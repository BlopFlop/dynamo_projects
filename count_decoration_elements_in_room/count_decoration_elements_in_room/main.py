import clr
clr.AddReference("RevitAPI")
import Autodesk.Revit.DB as DB # noqa
clr.AddReference("RevitNodes")
import Revit # noqa
clr.ImportExtensions(Revit.Elements)
clr.ImportExtensions(Revit.GeometryConversion)
clr.AddReference('RevitServices')
import RevitServices.Persistence.DocumentManager as DocumentManager # noqa
import System.Type as Type # noqa
import System.Collections.Generic.List as List # noqa


FEC = DB.FilteredElementCollector
NAME_TRANSACITON_COUNT_DECOR = 'DYNAMO Подсчет отделки помещений'
NAME_TRANSACITON_SET_PAR_DECOR = 'DYNAMO Запись параметров отделки в помещения'
CLASS_ELEMENTS = [DB.Wall, DB.Floor, DB.Ceiling, DB.WallSweep]

revit_document = DocumentManager.Instance.CurrentDBDocument

uiapp = DocumentManager.Instance.CurrentUIApplication
app = uiapp.Application
uidoc = uiapp.ActiveUIDocument

DYN_BOOL_CALC_ROOM_WRITE_VAL_FINISH = IN[0] # noqa
DYN_BOOL_VAR_SORT_IN_DATA = IN[1] # noqa
DYN_NAME_SCHEDULE = IN[2] # noqa
DYN_NAME_RECORDING_VAL_ROOM_IN_DECORATION = IN[3:7] # noqa
DYN_NAME_RECORDING_VAL_DECORATION_IN_ROOM = IN[7] # noqa


class SelectException(Exception):
    '''Ошибка выбора элементов.'''
    pass


class ParameterException(Exception):
    '''Ошибка параметра'''
    pass


def flatten(element, flat_list=None):
    '''Раскрытие вложенности списков.'''
    if flat_list is None:
        flat_list = []
    if hasattr(element, "__iter__"):
        for item in element:
            flatten(item, flat_list)
    else:
        flat_list.append(element)
    return flat_list


def transaction(t_name='Transaction'):
    '''Функция декоратор транзакции.'''
    def decorator(func):
        def wrappper(*args, **kwargs):
            with DB.Transaction(revit_document, t_name) as t:
                t.Start()
                func_call = func(*args, **kwargs)
                t.Commit()
            return func_call
        return wrappper
    return decorator


def unit_conventer(
        value,
        to_internal=False,
        unit_type=DB.UnitType.UT_Length,
        number_of_digits=None):
    '''Конвертер единиц ревит.'''
    display_units = (
        revit_document.GetUnits().GetFormatOptions(unit_type).DisplayUnits
    )
    method = DB.UnitUtils.ConvertToInternalUnits if to_internal \
        else DB.UnitUtils.ConvertFromInternalUnits
    if number_of_digits is None:
        return method(value, display_units)
    elif number_of_digits > 0:
        return round(method(value, display_units), number_of_digits)
    return int(round(method(value, display_units), number_of_digits))


def get_parameter_value(parameter):
    '''Получение значений параметра.'''
    if isinstance(parameter, DB.Parameter):
        storage_type = parameter.StorageType
        if storage_type == DB.StorageType.Integer:
            return parameter.AsInteger()
        elif storage_type == DB.StorageType.Double:
            return parameter.AsDouble()
        elif storage_type == DB.StorageType.String:
            return parameter.AsString()
        elif storage_type == DB.StorageType.ElementId:
            return parameter.AsValueString()


def clean_parameters_in_element(element, parameter_name):
    '''Чистка значений параметров в элементах'''
    parameter = element.LookupParameter(parameter_name)
    if parameter:
        value = get_parameter_value(parameter)
        if value:
            set_value = '' if isinstance(value, str) else 0
            parameter.Set(set_value)


def get_selection_rooms():
    '''Получение выбранных в Revit помещений.'''
    except_message = 'Вы не выбрали ни одного помещения'
    rooms = [
        revit_document.GetElement(room)
        for room in uidoc.Selection.GetElementIds()
        if isinstance(revit_document.GetElement(room), DB.Architecture.Room)
    ]
    if not rooms:
        raise SelectException(except_message)
    return rooms


def get_name_schedule(data=DYN_NAME_SCHEDULE[1:]):
    '''Получение имен спецификаций из исходных данных Excel DYNAMO.'''
    return [item[0] for item in data if item[0]]


def get_project_par_decoration_and_room(
        data=DYN_NAME_RECORDING_VAL_ROOM_IN_DECORATION):
    '''
    Получение имен параметров проекта помещений из Excel таблицы.
    Возвращаемое значение:
    result: dict[DB.ClassElement: list[str]]
    '''
    result = {}
    for i in range(len(CLASS_ELEMENTS)):
        name_parameters = [
            name_par[0:2] for name_par in data[i][1:]
            if name_par
            if name_par[0] and name_par[1]
        ]
        if name_parameters:
            result[CLASS_ELEMENTS[i]] = name_parameters
    return result


def get_project_par_room_and_decoration(
        data=DYN_NAME_RECORDING_VAL_DECORATION_IN_ROOM):
    '''
    Получение имен параметров проекта отделки из Excel таблицы.
    возвращаемое значение: list[str]
    '''
    result = []
    for item in data[1:]:
        if item and all(item):
            item = [
                item[0],
                item[1],
                True if item[2].lower() == 'да' else False
            ]
            result.append(item)
    return result


def get_name_type_for_view_schedule():
    '''Получение имен типоразмеров отображенных в спецификации.'''
    name_schedules = get_name_schedule()
    schedules = [
        schedule for schedule in FEC(revit_document).OfClass(DB.ViewSchedule)
        if schedule.Name in name_schedules
    ]
    names_type = []
    for schedule in schedules:
        type_elements_in_schedule = (
            FEC(revit_document, schedule.Id).WhereElementIsNotElementType()
        )
        for element in type_elements_in_schedule:
            names_type.append(
                element.Parameter[
                    DB.BuiltInParameter.ELEM_TYPE_PARAM].AsValueString()
            )
    return list(set(names_type))


def check_parameters(element, parameters_name):
    '''Проверка элемента на наличие необходимых параметров.'''
    cat_name = element.Category.Name
    element_type = revit_document.GetElement(element.GetTypeId())
    result = []

    for parameter_name in parameters_name:
        if element_type:
            if not (element.LookupParameter(parameter_name)
                    or element_type.LookupParameter(parameter_name)):
                result.append(parameter_name)
        elif not element.LookupParameter(parameter_name):
            result.append(parameter_name)

    if result:
        result = ', '.join(result)
        except_message = (
            'У категории {} отсутвуют параметры: {}'.format(
                cat_name, result
            )
        )
        raise ParameterException(except_message)


def check_str_type_par(parameter):
    except_message = (
        'Тип данных в параметре {} должен быть "Текст"'.format(
            parameter.Definition.Name
        )
    )
    if parameter.StorageType != DB.StorageType.String:
        raise ParameterException(except_message)


def check_parameter_in_all_element(
        room, data_room_in_decoration, data_decoraiton_in_room):
    '''Проверка наличия всех параметров в элементах'''
    check_par_room = room
    parameters = [
        values[i][1]
        for values in data_room_in_decoration.values()
        for i in range(len(values))
    ]
    if DYN_BOOL_CALC_ROOM_WRITE_VAL_FINISH:
        for i in range(len(data_decoraiton_in_room)):
            parameters.append(data_decoraiton_in_room[i][0])
    check_par_room = (
        check_parameters(check_par_room, parameters)
    )

    for class_elt in CLASS_ELEMENTS:
        element = FEC(revit_document).OfClass(class_elt).FirstElement()
        if element:
            values = data_room_in_decoration.get(class_elt)
            parameters = []
            if values:
                if DYN_BOOL_CALC_ROOM_WRITE_VAL_FINISH:
                    parameters += [
                        data_decoraiton_in_room[i][1]
                        for i in range(len(data_decoraiton_in_room))
                    ]
                for i in range(len(values)):
                    parameters.append(values[i][0])
                check_parameters(element, parameters)


def get_all_element_for_name_type(name_finish_rooms, classes):
    '''
    Функция получающая все элементы в документе исходя из имен типоразмеров.

    Переменные:
        document - Объект документа
        name_finish_room - имена типоразмеров
        classes - классы объектов по которым происходит сортировка
    '''
    list_type = List[Type]()
    for cls in classes:
        list_type.Add(cls)
    all_elements_for_name_type = {
        element.Id.IntegerValue: element for element in FEC(
            revit_document).WherePasses(DB.ElementMulticlassFilter(list_type))
        if element.Parameter[
            DB.BuiltInParameter.ELEM_TYPE_PARAM
        ].AsValueString() in name_finish_rooms
    }
    return all_elements_for_name_type


def get_solid(element, options):
    '''Получение солидов элемента.'''
    return [
        solid for solid in element.Geometry[options]
        if isinstance(solid, DB.Solid)
    ][0]


def is_point_in_room_for_xyz_wall(room, wall, solid):
    '''
    Фукция is_poin_in_room_for_xyz, возвращает True/False
    в зависимости от того найдет ли точку в помещении

    Переменные:
    document - объект документа,
    room - объект комнаты,
    wall - объект стены,
    solid - тело геометрии объекта,

    Возвращает:
    True/False
    '''

    orientation = wall.Orientation.Normalize() * wall.Width/2
    central_point = solid.ComputeCentroid()
    wall_location_line_direction = (
        wall.Location.Curve.Direction.Normalize() * wall.Width/2)

    point_1 = central_point
    point_2 = point_1 + orientation
    point_3 = point_1 - orientation
    point_4 = point_2 + wall_location_line_direction
    point_5 = point_2 - wall_location_line_direction
    point_6 = point_3 + wall_location_line_direction
    point_7 = point_3 - wall_location_line_direction

    points = [
        room.IsPointInRoom(point) for point in [
            point_1, point_2, point_3, point_4, point_5, point_6, point_7
        ] if room.IsPointInRoom(point)
    ]
    return any(points)


def is_point_in_room_for_xyz_floor_or_ceiling(room, element, solid):
    '''
    Получение точек геометрии пола и потолка и
    проверка на нахождение их в помещении
    '''
    width = revit_document.GetElement(
        element.GetTypeId()).GetCompoundStructure().GetWidth()

    geometry_direction = width/2 * DB.XYZ(0, 0, 1).Normalize()
    central_point = solid.ComputeCentroid()

    point_1 = central_point + geometry_direction
    point_2 = central_point - geometry_direction

    for point in [central_point, point_1, point_2]:
        if room.IsPointInRoom(point):
            return True
    return False


def append_element_for_xyz_in_room(
        element_for_room_geometry,
        all_element_for_name_type):
    """
    Поиск отделки помещений
        Стены - по координатам угловых точек
        Перекрытия - по координате центральной точки
        Потолки - по координате центральной точки

    Переменные:
        document - объект помещения
        element_for_room_geometry - Переменная полученная с помощью функции
            get_element_for_room_geometry()
        all_element_for_name_type - Список с элементами отделки, которые не
            были найдены с помощью функции get_element_for_room_geometry

    Функция возвращает:
    {
    Room <Ключ, объект помещения> :
        [
            [Wall <0-й влженный список, объекты стен>],
            [Floor <1-й вложенный список, объекты полов>],
            [Ceiling <2-й вложенный список, объекты полов>]
        ]
    }
    """
    options = DB.Options()
    options.DetailLevel = DB.ViewDetailLevel.Coarse

    walls = []
    floors = []
    ceilings = []

    for element in all_element_for_name_type:
        if isinstance(element, CLASS_ELEMENTS[0]):
            walls.append(element)
        if isinstance(element, CLASS_ELEMENTS[1]):
            floors.append(element)
        if isinstance(element, CLASS_ELEMENTS[2]):
            ceilings.append(element)

    for room in element_for_room_geometry:

        if walls:
            for wall in walls:
                solid = get_solid(wall, options)
                try:
                    is_point = is_point_in_room_for_xyz_wall(
                        room, wall, solid
                    )
                except Exception:
                    is_point = False
                if is_point and wall.Id.IntegerValue:
                    element_for_room_geometry[room][0].append(wall)

        if floors:
            for floor in floors:
                solid = get_solid(floor, options)
                if is_point_in_room_for_xyz_floor_or_ceiling(
                        room, floor, solid):
                    element_for_room_geometry[room][1].append(floor)

        if ceilings:
            for ceiling in ceilings:
                solid = get_solid(ceiling, options)
                if is_point_in_room_for_xyz_floor_or_ceiling(
                        room, ceiling, solid):
                    element_for_room_geometry[room][2].append(ceiling)

    for room in element_for_room_geometry.keys():
        values = element_for_room_geometry.get(room)
        element_for_room_geometry[room] = [
            {value.Id.IntegerValue: value for value in values[0]}.values(),
            {value.Id.IntegerValue: value for value in values[1]}.values(),
            {value.Id.IntegerValue: value for value in values[2]}.values(),
        ]

    return element_for_room_geometry


def append_element_for_wallsweep(
        element_for_room_geometry,
        all_element_for_name_type):
    """
    Добавление плинтусов помещений

    Переменные:
        document - объект помещения
        element_for_room_geometry - Переменная полученная с помощью функции
            get_element_for_room_geometry()
        all_element_for_name_type - Список с элементами отделки, которые не
            были найдены с помощью функции get_element_for_room_geometry

    Функция возвращает:
    {
    Room <Ключ, объект помещения> : {
        [
            [Wall <0-й влженный список, объекты стен>],
            [Floor <1-й вложенный список, объекты полов>],
            [Ceiling <2-й вложенный список, объекты потолков>],
            [WallSweep <3-й вложенный список, объекты плинтуса>]
        ]
    }
    """
    for room in element_for_room_geometry.keys():
        element_for_room_geometry[room].append([])
    wallsweeps = {
        element: [
            host_element.IntegerValue for host_element in element.GetHostIds()
        ] for element in all_element_for_name_type
        if isinstance(element, CLASS_ELEMENTS[3])}
    for wallsweep in wallsweeps.keys():
        host_walls_id = wallsweeps.get(wallsweep)
        for room, value in element_for_room_geometry.items():
            walls_id = [wall.Id.IntegerValue for wall in value[0]]
            for host_wall_id in host_walls_id:
                if host_wall_id in walls_id:
                    element_for_room_geometry[room][3].append(wallsweep)
                    break
    return element_for_room_geometry


def get_element_for_room_geometry(rooms, name_finish_rooms):
    """
    Поиск элементов создавших геометрию помещения и вывод
    словаря, где ключом является помещение, а значением является список
    с 3-мя вложенными списками.
    *Коллизии:
        некоторые элементы невозможно получить по поиску геометрии
        (Обычно из-за маленького размера эл-та или он весь входит в помещение),
        поэтому в конце функции происходит вызов функции, куда передается
        список элементов во всем проекте соответсвующий именам типоразмера
        (исключая те элементы, которые алгоритм нашел по геометрии), и
        идет поиск по координатным точкам геометрии
        по алгоритму функции.
    Переменные:
        document - документ в котором ведется работа
        rooms - помещения
        name_finish_room - имя типоразмеров отделки помещений
    Функция возвращает:
    {
    Room <Ключ, объект помещения> :
        [
            [Wall <0-й влженный список, объекты стен>],
            [Floor <1-й вложенный список, объекты полов>],
            [Ceiling <2-й вложенный список, объекты полов>],
            [WallSweep <3-й вложенный список, объекты плинтусов>]
        ]
    }
    """
    all_element_for_name_type = get_all_element_for_name_type(
        name_finish_rooms, CLASS_ELEMENTS
    )

    Options = DB.SpatialElementBoundaryOptions()
    Options.StoreFreeBoundaryFaces = True
    Options.SpatialElementBoundaryLocation = (
        DB.SpatialElementBoundaryLocation.Finish)
    Splatian = DB.SpatialElementGeometryCalculator(revit_document, Options)

    element_for_room_geometry = {}

    remove_list_element_for_name_type = [
        elments_id for elments_id in all_element_for_name_type]

    for room in rooms:
        calculator = Splatian.CalculateSpatialElementGeometry(room)
        geometry = flatten(calculator.GetGeometry().Faces)

        faces_info = [
            flatten(calculator.GetBoundaryFaceInfo(solid))
            for solid in geometry
        ]

        elements = []
        for face_info in flatten(faces_info):
            if isinstance(face_info, DB.SpatialElementBoundarySubface):
                bip_type = DB.BuiltInParameter.ELEM_TYPE_PARAM
                element = revit_document.GetElement(
                    face_info.SpatialBoundaryElement.HostElementId
                )
                if element:
                    parameter = element.Parameter[bip_type].AsValueString()
                    if parameter in name_finish_rooms:
                        elements.append(element)

        element_for_room_geometry[room] = [[], [], [], []]

        for element in elements:
            if element.Id.IntegerValue in remove_list_element_for_name_type:
                remove_list_element_for_name_type.remove(
                    element.Id.IntegerValue
                )
            if isinstance(element, CLASS_ELEMENTS[0]):
                element_for_room_geometry[room][0].append(element)
            elif isinstance(element, CLASS_ELEMENTS[1]):
                element_for_room_geometry[room][1].append(element)
            elif isinstance(element, CLASS_ELEMENTS[2]):
                element_for_room_geometry[room][2].append(element)

    all_element_for_name_type = [
        all_element_for_name_type.get(element_id)
        for element_id in remove_list_element_for_name_type
    ]

    element_for_room_geometry = append_element_for_xyz_in_room(
        element_for_room_geometry, all_element_for_name_type
    )
    return element_for_room_geometry


def sort_el_type_and_instance(elements):
    '''Сортировка элементов и формирование словаря, где ключем
    является идентификатор типа, а значением экземпляры типа.'''
    type_elements = {
        element.GetTypeId().IntegerValue: [] for element in elements
        if element.GetTypeId().IntegerValue
    }
    for element in elements:
        type_elements[element.GetTypeId().IntegerValue].append(element)
    return type_elements


def union_parameter_instance(instances, parameter_name):
    '''Объединение значений параметров у экземпляров'''
    result = []
    for instance in instances:
        parameter = instance.LookupParameter(parameter_name[0])
        parameter_value = get_parameter_value(parameter)

        if parameter.StorageType == DB.StorageType.String:
            repl_value = '-'
        else:
            repl_value = 0

        result.append(parameter_value if parameter_value else repl_value)

    parameter_unit_type = parameter.Definition.UnitType

    if isinstance(result[0], str):
        result = ', '.join(result)
    else:
        value = unit_conventer(
            sum(result), False, parameter_unit_type
        )
        result = round(value, 2)
        if parameter_unit_type == DB.DisplayUnitType.DUT_MILLIMETERS:
            result = round(result/1000, 2)

    return result


def sort_data_decoraitons(data):
    '''Выравнивание параметров между друг другом'''
    sort_symbol = '\n'

    for el_type, set_parameters in data.items():
        result = []
        max_len_elt = max(
            [
                str(data_item).count(sort_symbol)
                for dict_par in set_parameters
                for data_item in dict_par.values()
            ]
        )
        for dict_par in set_parameters:
            for name_par, data_item in dict_par.items():
                count_sort_symbol = (
                    str(data_item).count(sort_symbol)
                )
                diff = max_len_elt - count_sort_symbol
                if max_len_elt == count_sort_symbol:
                    result.append({name_par: data_item})
                elif diff % 2:
                    start_element = (diff//2 + 1) * sort_symbol
                    end_element = diff//2 * sort_symbol
                    value = start_element + str(data_item) + end_element
                    result.append({name_par: value})
                else:
                    insert_elt = diff//2 * sort_symbol
                    value = insert_elt + str(data_item) + insert_elt
                    result.append({name_par: value})
        data[el_type] = result
    return data


def set_parameter_room_in_decoration(
        room,
        decoraiton_elts,
        parameters,
        sort_data):
    '''Добавление значений параметров отделки помещений в помещения'''
    decoraiton_elts = sort_el_type_and_instance(decoraiton_elts)
    decoration_parameters = {
        el_type: [] for el_type in decoraiton_elts.keys()
    }

    for el_type, el_instances in decoraiton_elts.items():
        el_type = revit_document.GetElement(DB.ElementId(el_type))
        for parameter in parameters:
            parameter_el_type = el_type.LookupParameter(parameter[0])
            if parameter_el_type:
                result_value = get_parameter_value(parameter_el_type)
            else:
                result_value = union_parameter_instance(
                    el_instances, parameter
                )
            decoration_parameters[el_type.Id.IntegerValue].append(
                    {parameter[1]: (result_value if result_value else '-')}
                )

    if sort_data:
        decoration_parameters = (
            sort_data_decoraitons(decoration_parameters)
        )

    sort_parameters = {}
    for values in decoration_parameters.values():
        for value in values:
            for key, item in value.items():
                if key not in sort_parameters.keys():
                    sort_parameters[key] = []
                sort_parameters[key].append(item)

    for parameter_name, value in sort_parameters.items():
        value = [str(item) for item in value]
        parameter = room.LookupParameter(parameter_name)
        check_str_type_par(parameter)
        parameter.Set(('\n\n'.join(value)))


@transaction(t_name=NAME_TRANSACITON_COUNT_DECOR)
def add_decor_elt_in_par_room(
        decoration_elts,
        data_room_in_decoration,
        sort_data):
    '''
    Добавление параметров отделки помещений в параметры комнат.
    Алгоритм записи параметров >>> объединяя параметры с различных
    типоразмеров в один параметр комнаты, мы разделяем
    данные символом "\n" - если все параметры однострочные.
    Пример:
    <1 Поле спецификции, одна строка> - <2 Поле спецификции, одна строка>

    Если параметры многострочные то передаем в переменную boolean - True то,
    для того чтобы в ячейках выравнивались данные относительно друг друга.

    Пример:
    <1 Поле спецификции, 5 строк>   < \n >                              <\n>
    <          Строка 2         >   < \n >                              3
    <          Строка 3         > - <2 Поле спецификции, одна строка> - 4
    <          Строка 4         >   < \n >                              5
    <          Строка 5         >   < \n >                              <\n>

    Переменные:
        document - документ в котором ведется работа
        room_finish - словарь с оделкой, который возвращает функция
            get_element_for_room_geometry
        dict_get_and_set_parameter_names - словарь, с именами
            параметров отделки и параметров помещения
        boolean - Выравнивать ли информацию, если она многострочная

    Функция возвращает - неизменный словарь room_finish
    '''
    for room in decoration_elts.keys():
        for values in data_room_in_decoration.values():
            for parameter in values:
                clean_parameters_in_element(room, parameter[1])

    for room, values in decoration_elts.items():
        for decoration_elts in values:
            if decoration_elts:
                parameters = (
                    data_room_in_decoration.get(type(decoration_elts[0]))
                )
                set_parameter_room_in_decoration(
                    room, decoration_elts, parameters, sort_data
                )
    return decoration_elts


def sort_list_int_in_str(values):
    """
    Сортировка строк в которых есть цифры, по возрастанию
    по правилам сортировки цифрового типа данных.
    """
    sort_dict = {}
    for value in values:
        value_int = [i for i in value if i.isdigit()]
        if len(value_int):
            value_int = int(''.join(value_int))
            sort_dict[value_int] = value
    if sort_dict:
        return [
            sort_dict.get(value_int)
            for value_int in sorted(sort_dict.keys())]
    else:
        return set(values)


@transaction(t_name=NAME_TRANSACITON_SET_PAR_DECOR)
def set_finish_parameter_for_numbers_room(
        decoration_elts,
        item_data_parameters):
    '''
    Добавление параметров помещения в параметры финишной отделки с 2 мя
    алгоритмами записи:
        1) Запись значений параметров помещений в параметры экземпляров,
        которые ссылаются на один и тот же типоразмер
        объединенных знак " ,".
            Пример: Отделка под именем типоразмера "Типовой 200" экземпляры
            которого находятся в помещении ROOM1 и ROOM2
            и параметр помещения "Номер" необходимо перенести в параметр
            экземпляров "Номера помещени", после выполненния
            данной функции значения параметров экземпляров будут "1, 2"

        2) Запись значения параметра помещений в параметры экземпляров в
            помещении которого они находятся.
            Пример: Все экземпляры отделки находящиеся в помещении будут
            иметь одно и то же значение параметра.

    Переменные:
        decoration_elts - Переменная где хранится словарь с объектами
            помещений и ее отделки.
        item_data_parameters - список где хранятся
            имена параметров помещения и парметров
        экземпляров, а также объединять или нет параметры [
            "Имя параметра помещения", "Имя параметра отделки", True/False]
    '''

    instances = flatten(decoration_elts.values())

    type_instances = sort_el_type_and_instance(instances)

    type_rooms = {
        type_instance: [] for type_instance in type_instances.keys()
    }
    for room, instances in decoration_elts.items():
        instances = flatten(instances)
        for instance in instances:
            type_rooms[instance.GetTypeId().IntegerValue].append(room)

    for room_par, inst_par, union_par in item_data_parameters:
        if union_par:
            for type_instance in type_instances.keys():
                room_values = []

                for room in type_rooms.get(type_instance):
                    value = get_parameter_value(room.LookupParameter(room_par))
                    room_values.append(str(value) if value else '-')

                for instance in type_instances.get(type_instance):
                    parameter = instance.LookupParameter(inst_par)
                    check_str_type_par(parameter)
                    room_values = sorted(set(room_values))
                    parameter.Set(', '.join(room_values))
        else:
            for room, instances in decoration_elts.items():
                for instance in flatten(instances):
                    value = get_parameter_value(room.LookupParameter(room_par))
                    parameter = instance.LookupParameter(inst_par)
                    check_str_type_par(parameter)
                    parameter.Set(value if value else '-')
    return decoration_elts


def main():
    rooms = get_selection_rooms()
    type_name_decoration = get_name_type_for_view_schedule()
    data_room_in_decoration = get_project_par_decoration_and_room(
        DYN_NAME_RECORDING_VAL_ROOM_IN_DECORATION
    )
    data_decoraiton_in_room = get_project_par_room_and_decoration(
        DYN_NAME_RECORDING_VAL_DECORATION_IN_ROOM
    )
    check_parameter_in_all_element(
        rooms[0], data_room_in_decoration, data_decoraiton_in_room
    )
    decoration_elts = get_element_for_room_geometry(
        rooms, type_name_decoration
    )
    add_decor_elt_in_par_room(
        decoration_elts, data_room_in_decoration, DYN_BOOL_VAR_SORT_IN_DATA
    )
    if DYN_BOOL_CALC_ROOM_WRITE_VAL_FINISH:
        set_finish_parameter_for_numbers_room(
            decoration_elts, data_decoraiton_in_room
        )
    return decoration_elts.values()


OUT = main()
