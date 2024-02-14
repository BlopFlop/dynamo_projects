import clr
clr.AddReference('RevitAPI')
import Autodesk.Revit.DB as DB # noqa
clr.AddReference("RevitServices")
import RevitServices.Persistence.DocumentManager as DocumentManager # noqa

import System.Collections.Generic.List as List # noqa


DOC = DocumentManager.Instance.CurrentDBDocument
UIAPP = DocumentManager.Instance.CurrentUIApplication
APP = UIAPP.Application
UIDOC = UIAPP.ActiveUIDocument

FEC = DB.FilteredElementCollector

TRANSACTION_NAME = 'DYNAMO Копирование листов'
DYN_NEED_TO_COPY_VIEWPORT = IN[0] # noqa


class SelecitonException(Exception):
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


def transaciton(t_name='DYNAMO Skript'):
    '''Декоратор транзакции.'''
    def decorator(func):
        def wrapper(*args, **kwargs):
            with DB.Transaction(DOC, t_name) as t:
                t.Start()
                result_func = func(*args, **kwargs)
                t.Commit()
            return result_func
        return wrapper
    return decorator


def get_selection_elts():
    '''Получение выбранных в интерфейсе Revit элементов.'''
    selecton_elts = [
        DOC.GetElement(room) for room in UIDOC.Selection.GetElementIds()
        if isinstance(DOC.GetElement(room), DB.ViewSheet)
    ]
    if not selecton_elts:
        except_message = 'Вы не выбрали ни одного листа.'
        raise SelecitonException(except_message)
    return selecton_elts


def copy_parameters_sheet(source_sheet, desc_sheet):
    '''Копирование параметров листа.'''
    source_parameters = {
        par.Id.IntegerValue: par for par in source_sheet.ParametersMap
    }
    desc_parameters = {
        par.Id.IntegerValue: par for par in desc_sheet.ParametersMap
        if not par.IsReadOnly
    }

    id_par_number_sheet = -1007401
    value_number_sheer = get_parameter_value(
        source_parameters.get(id_par_number_sheet)
    )
    desc_parameters.pop(id_par_number_sheet).Set(value_number_sheer + '_Копия')

    for source_par_id, source_par in source_parameters.items():
        source_par = get_parameter_value(source_par)
        desc_par = desc_parameters.get(source_par_id)
        if desc_par and source_par:
            desc_par.Set(source_par)


def copy_elements_in_sheet(
        source_sheet, copy_sheet, need_to_copy_viewport=False):
    '''Копирование элементов расположенных на листе.'''
    collector = FEC(DOC, source_sheet.Id)

    cat_id_guide_grid = -2000107
    elements = [
        element for element in collector.WhereElementIsNotElementType()
        if element.Category.Id.IntegerValue != cat_id_guide_grid
    ]

    viewports = []
    collect_list = List[DB.ElementId]()
    for element in elements:
        if not isinstance(element, DB.Viewport):
            collect_list.Add(element.Id)
        elif isinstance(element, DB.Viewport):
            viewports.append(element)

    DB.ElementTransformUtils.CopyElements(
        source_sheet,
        collect_list,
        copy_sheet,
        DB.Transform.Identity,
        DB.CopyPasteOptions(),
    )

    if not need_to_copy_viewport:
        viewports = []

    for viewport in viewports:
        duplicate_opt = DB.ViewDuplicateOption.WithDetailing
        copy_view_id = DOC.GetElement(viewport.ViewId).Duplicate(duplicate_opt)
        DB.Viewport.Create(
            DOC,
            copy_sheet.Id,
            copy_view_id,
            viewport.GetBoxCenter()
        )


@transaciton(t_name=TRANSACTION_NAME)
def main():
    sheets = get_selection_elts()
    for sheet in sheets:
        new_sheet = DB.ViewSheet.Create(DOC, DB.ElementId.InvalidElementId)
        copy_parameters_sheet(sheet, new_sheet)
        copy_elements_in_sheet(sheet, new_sheet, DYN_NEED_TO_COPY_VIEWPORT)


main()
