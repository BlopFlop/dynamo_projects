import clr
clr.AddReference("RevitAPI")
import Autodesk.Revit.DB as DB # noqa
clr.AddReference("RevitNodes")
clr.AddReference("RevitServices")
import RevitServices.Persistence.DocumentManager as DocumentManager # noqa


FEC = DB.FilteredElementCollector

SET_NAME_SCHEDULE = 'ИзмКат_'
NAME_TRANSACTION = 'DYNAMO Изменение категории спецификации.'

UIAPP = DocumentManager.Instance.CurrentUIApplication
DOC = DocumentManager.Instance.CurrentDBDocument
APP = UIAPP.Application
UIDOC = UIAPP.ActiveUIDocument

DYN_CATEGORY = DB.ElementId(IN[0].Id) # noqa


class SelectException(Exception):
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


def transaciton(t_name=NAME_TRANSACTION):
    '''Функция декоратор транзакции'''
    def decorator(func):
        def wrapper(*args, **kwargs):
            with DB.Transaction(DOC, t_name) as t:
                t.Start()
                result = func(*args, **kwargs)
                t.Commit()
            return result
        return wrapper
    return decorator


def get_select_schedule():
    '''Получение выбираемых спецификаций.'''
    select_element = [
        DOC.GetElement(select_element)
        for select_element in UIDOC.Selection.GetElementIds()
    ]
    if select_element:
        return select_element[0]
    raise SelectException('Вы не выбрали ни одной спецификации.')


def copy_all_parameters(fst_sch_par, scd_set_sch_par):
    '''Копирует значение параметров из одной спецификации к другой'''
    dict_fst_sch_par = {
        set_par.Id.IntegerValue: set_par for set_par in fst_sch_par
        if not set_par.IsReadOnly if set_par.HasValue
    }
    dict_pars = {
        par.Id.IntegerValue: par for par in scd_set_sch_par
        if not par.IsReadOnly
    }
    dict_fst_sch_par.pop(-1005112)
    for par_id in dict_fst_sch_par.keys():
        set_par = dict_pars.get(par_id)
        fst_sch_par = dict_fst_sch_par.get(par_id)
        if set_par and fst_sch_par:
            set_par.Set(get_parameter_value(fst_sch_par))


def copy_parameter_schedule(fst_schedule, scd_schedule):
    '''Копирует параметры класса спецификации DB.ViewSchedule,
    а так же значения параметров.'''
    fst_schedule_params = fst_schedule.ParametersMap
    scd_schedule_params = scd_schedule.ParametersMap
    copy_all_parameters(fst_schedule_params, scd_schedule_params)
    scd_schedule.Pinned = fst_schedule.Pinned
    fst_cat_name = (
        FEC(DOC, fst_schedule.Id).FirstElement().Category.Name
    )
    scd_cat_name = DB.Category.GetCategory(DOC, DYN_CATEGORY).Name
    set_name = '_'.join(
        (
            fst_schedule.Name,
            SET_NAME_SCHEDULE,
            '{}_на_{}'.format(fst_cat_name, scd_cat_name)
        )
    )
    scd_schedule.Name = set_name
    scd_schedule.BodyTextTypeId = fst_schedule.BodyTextTypeId
    scd_schedule.HasStripedRows = fst_schedule.HasStripedRows
    scd_schedule.HeaderTextTypeId = fst_schedule.HeaderTextTypeId
    if fst_schedule.ImageRowHeight:
        scd_schedule.ImageRowHeight = fst_schedule.ImageRowHeight
    if fst_schedule.IsHeaderFrozen:
        scd_schedule.IsHeaderFrozen = fst_schedule.IsHeaderFrozen
    try:
        scd_schedule.KeyScheduleParameterName = (
            fst_schedule.KeyScheduleParameterName
        )
    except Exception:
        pass
    scd_schedule.TitleTextTypeId = fst_schedule.TitleTextTypeId
    scd_schedule.UseStripedRowsOnSheets = fst_schedule.UseStripedRowsOnSheets


def get_all_fields(schedule_definition):
    '''Получение всех полей в спецификации.'''
    return [
        schedule_definition.GetField(i)
        for i in range(schedule_definition.GetFieldCount())
    ]


def copy_parameter_field(fst_field, scd_field):
    '''Копирование параметров класса поля спецификации.'''
    scd_field.ColumnHeading = fst_field.ColumnHeading
    try:
        scd_field.DisplayType = fst_field.DisplayType
    except Exception:
        pass
    scd_field.GridColumnWidth = fst_field.GridColumnWidth
    scd_field.HeadingOrientation = fst_field.HeadingOrientation
    scd_field.HorizontalAlignment = fst_field.HorizontalAlignment
    scd_field.IsHidden = fst_field.IsHidden
    try:
        scd_field.PercentageBy = fst_field.PercentageBy
    except Exception:
        pass
    try:
        scd_field.PercentageOf = fst_field.PercentageOf
    except Exception:
        pass
    scd_field.SheetColumnWidth = fst_field.SheetColumnWidth
    try:
        scd_field.TotalByAssemblyType = fst_field.TotalByAssemblyType
    except Exception:
        pass
    scd_field.SetStyle(fst_field.GetStyle())
    scd_field.SetFormatOptions(fst_field.GetFormatOptions())


def copy_fileds(fst_definition, scd_definition):
    '''Копирование полей и их параметров.'''
    fst_fields = get_all_fields(fst_definition)
    scd_schedulable_fields = {
        scd_field.GetHashCode(): scd_field
        for scd_field in scd_definition.GetSchedulableFields()
    }
    for field in fst_fields:
        if not field.HasSchedulableField:
            continue
        hash_code = field.GetSchedulableField().GetHashCode()
        scd_field = scd_schedulable_fields.get(hash_code)
        if scd_field:
            new_schedule_field = scd_definition.AddField(scd_field)
            copy_parameter_field(field, new_schedule_field)


def add_filter_and_sort_group(
        fst_definition, scd_definition, scd_fields, method='get_filter'):
    '''Добавление фильтров и сортировку/группировку в спецификацию.'''
    GET_FILTER = 'get_filter'
    GET_SORT_GROUP = 'get_sort'

    if method == GET_FILTER:
        items = fst_definition.GetFilters()
    elif method == GET_SORT_GROUP:
        items = fst_definition.GetSortGroupFields()

    for item in items:
        fst_field = fst_definition.GetField(item.FieldId)
        fst_parameter_id = fst_field.ParameterId.IntegerValue
        scd_field = scd_fields.get(fst_parameter_id)
        if scd_field:
            item.FieldId = scd_field.FieldId
            if method == GET_FILTER:
                scd_definition.AddFilter(item)
            elif method == GET_SORT_GROUP:
                scd_definition.AddSortGroupField(item)


def copy_filters_and_sort_group(select_schedule, new_schedule):
    '''Копирование фильтров и сортировки/группирования
    в определение спецификации'''
    fst_definition = select_schedule.Definition
    scd_definition = new_schedule.Definition
    scd_fields = {}
    for i in range(scd_definition.GetFieldCount()):
        field = scd_definition.GetField(i)
        parameter_id = field.ParameterId.IntegerValue
        scd_fields[parameter_id] = field

    add_filter_and_sort_group(
        fst_definition, scd_definition, scd_fields, method='get_filter'
    )
    add_filter_and_sort_group(
        fst_definition, scd_definition, scd_fields, method='get_sort'
    )


def copy_definition_schedule(fst_schedule, scd_schedule):
    fst_definition = fst_schedule.Definition
    scd_definition = scd_schedule.Definition
    try:
        scd_definition.GrandTotalTitle = fst_definition.GrandTotalTitle
    except Exception:
        pass
    scd_definition.IncludeLinkedFiles = fst_definition.IncludeLinkedFiles
    scd_definition.IsItemized = fst_definition.IsItemized
    if fst_definition.ShowGrandTotal:
        scd_definition.ShowGrandTotal = fst_definition.ShowGrandTotal
    if fst_definition.ShowGrandTotalCount:
        scd_definition.ShowGrandTotalCount = fst_definition.ShowGrandTotalCount
    if fst_definition.ShowGrandTotalTitle:
        scd_definition.ShowGrandTotalTitle = fst_definition.ShowGrandTotalTitle
    scd_definition.ShowGridLines = fst_definition.ShowGridLines
    scd_definition.ShowHeaders = fst_definition.ShowHeaders
    scd_definition.ShowTitle = fst_definition.ShowTitle
    copy_fileds(fst_definition, scd_definition)


@transaciton(t_name=NAME_TRANSACTION)
def set_class_schedule(select_schedule, set_category_id):
    '''Смена класса семейства в спецификации'''
    new_schedule = DB.ViewSchedule.CreateSchedule(DOC, set_category_id)
    DOC.Regenerate
    copy_parameter_schedule(select_schedule, new_schedule)
    DOC.Regenerate
    copy_definition_schedule(select_schedule, new_schedule)
    DOC.Regenerate
    copy_filters_and_sort_group(select_schedule, new_schedule)


select_schedule = get_select_schedule()
set_class_schedule(select_schedule, DYN_CATEGORY)
