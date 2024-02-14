import clr
clr.AddReference("RevitAPI")
import Autodesk.Revit.DB as DB
clr.AddReference("RevitNodes")
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager


TRANSACTION_NAME = 'DYNAMO Подсчет объема 3д геометрии'

DOC = DocumentManager.Instance.CurrentDBDocument
UIAPP = DocumentManager.Instance.CurrentUIApplication
APP = UIAPP.Application
UIDOC = UIAPP.ActiveUIDocument

FEC = DB.FilteredElementCollector

GEOM_OPTIONS = DB.Options()
GEOM_OPTIONS.DetailLevel = DB.ViewDetailLevel.Fine

DYN_NAME_VOLUME_PAR = IN[0]
# 'ADSK_Размер_Объем'


class SelecitonException(Exception):
    pass


class ParameterException(Exception):
    pass


class GeometryException(Exception):
    pass


def transaction(t_name='DYNAMO Script'):
    '''Функция декоратор транзакции.'''
    def wrapper(func):
        def decorator(*args, **kwargs):
            with DB.Transaction(DOC, t_name) as t:
                t.Start()
                result_func = func(*args, **kwargs)
                t.Commit()
            return result_func
        return decorator
    return wrapper


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


def get_selection_elts():
    '''Получение выбранных элементов'''
    selecton_elts = [
        DOC.GetElement(room) for room in UIDOC.Selection.GetElementIds()
    ]
    if not selecton_elts:
        except_message = 'Вы не выбрали ни одного элемента.'
        raise SelecitonException(except_message)
    return selecton_elts


def check_parameter(element):
    '''Проверка парамтера'''
    parameter = element.LookupParameter(DYN_NAME_VOLUME_PAR)
    if not parameter:
        except_message = (
            'Параметра {} нет в элементе с id {}'.format(
                DYN_NAME_VOLUME_PAR, element.Id.IntegerValue)
        )
        raise ParameterException(except_message)

    definition_par = parameter.Definition
    name_par = definition_par.Name
    if definition_par.ParameterType != DB.ParameterType.Volume:
        except_message = (
            'Тип данных параметера {} не объем'.format(
                name_par
            )
        )
        raise ParameterException(except_message)


def get_solid(g_elements, solids=None):
    '''Получение всех солидов в элементе'''
    g_elements = flatten(g_elements)
    if solids is None:
        solids = []
    for g_element in g_elements:
        if isinstance(g_element, DB.Solid):
            solids.append(g_element)
        elif isinstance(g_element, DB.GeometryInstance):
            g_elements = g_element.SymbolGeometry
            get_solid(g_elements, solids)
    return solids


@transaction(t_name=TRANSACTION_NAME)
def main():
    select_elts = get_selection_elts()
    for select_elt in select_elts:
        check_parameter(select_elt)
        g_elements = select_elt.Geometry[GEOM_OPTIONS]
        solids = get_solid(g_elements)
        if not solids:
            except_message = (
                'В элементе id {} не найдено геометрии'.format(
                    select_elt.Id.IntegerValue)
            )
            raise GeometryException(except_message)
        result_value = sum(
            [solid.Volume if solid.Volume > 0 else 0 for solid in solids]
        )
        select_elt.LookupParameter(DYN_NAME_VOLUME_PAR).Set(result_value)


main()
