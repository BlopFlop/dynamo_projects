import clr
clr.AddReference("RevitAPI")
import Autodesk.Revit.DB as DB
clr.AddReference('RevitServices')
from RevitServices.Persistence import DocumentManager


DOC = DocumentManager.Instance.CurrentDBDocument
UI_APP = DocumentManager.Instance.CurrentUIApplication
APP = UI_APP.Application
UI_DOC = UI_APP.ActiveUIDocument

FEC = DB.FilteredElementCollector
TRANSACTION_NAME = 'DYNAMO Трансфер значения параметров у вложенных элементов.'

SOURCE_NAME_PAR = IN[0]
DEST_NAME_PAR = IN[1]


class SelectException(Exception):
    pass


class ParmeterException(Exception):
    pass


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
            return parameter.AsElementId()


def transaction(t_name):
    def decorator(func):
        def wrapper(*args, **kwargs):
            with DB.Transaction(DOC, t_name) as t:
                t.Start()
                return_func = func(*args, **kwargs)
                t.Commit()
            return return_func
        return wrapper
    return decorator


def get_select_element():
    select_elements = [
        DOC.GetElement(elt) for elt in UI_DOC.Selection.GetElementIds()
    ]
    if not select_elements:
        except_message = 'Вы не выбрали ни одного элемента.'
        raise SelectException(except_message)
    return select_elements


def check_elt_in_par(elt, name_par):
    parameter = elt.LookupParameter(name_par)
    if not parameter:
        except_message = 'Параметра {} не существует'.format(name_par)
        raise ParmeterException(except_message)
    return parameter


def get_par_in_elt(elt, name_par):
    elt = DOC.GetElement(elt)
    type_elt = DOC.GetElement(elt.GetTypeId())
    parameter = elt.LookupParameter(name_par)
    if not parameter:
        parameter = type_elt.LookupParameter(name_par)
    return parameter if parameter else None


def set_parmeter_in_elt(source_par, dest_par):
    STORAGE_TYPE_NAME = {
        DB.StorageType.Integer: 'число',
        DB.StorageType.Double: 'физическое значение',
        DB.StorageType.String: 'текст',
        DB.StorageType.ElementId: 'элемент',
    }

    source_storage_type = source_par.StorageType
    dest_storage_type = dest_par.StorageType

    source_par_name = source_par.Definition.Name
    dest_par_name = dest_par.Definition.Name

    if source_storage_type != dest_storage_type:
        source_data_name = (
            STORAGE_TYPE_NAME.get(source_storage_type)
        )
        dest_data_name = (
            STORAGE_TYPE_NAME.get(dest_storage_type)
        )

        except_message = ''.join((
            'Типы данных переносимых парамтеров не совпадают ',
            '{} имеет тип данных: {} '.format(
                source_par_name, source_data_name),
            'а {} имеет тип данных: {}'.format(
                dest_par_name, dest_data_name)
        ))
        raise ParmeterException(except_message)
    elif dest_par.IsReadOnly:
        source_par_name
        except_message = 'Параметр {} в элементе ID: {}'.format(
            dest_par_name, dest_par.Element.Id.IntegerValue
        )
        raise ParmeterException(except_message)
    else:
        dest_par.Set(get_parameter_value(source_par))


@transaction(t_name=TRANSACTION_NAME)
def transfer_par_value(source_elts, source_name_par, dest_name_par):
    for source_elt in source_elts:
        source_par = check_elt_in_par(source_elt, source_name_par)
        elt_filter = DB.ElementClassFilter(DB.FamilyInstance)
        dest_elts = source_elt.GetDependentElements(elt_filter)
        for dest_elt in dest_elts:
            dest_par = get_par_in_elt(dest_elt, dest_name_par)
            if dest_par:
                set_parmeter_in_elt(source_par, dest_par)


selection = get_select_element()
transfer_par_value(selection, SOURCE_NAME_PAR, DEST_NAME_PAR)

OUT = 'Скрипт отработан.'
