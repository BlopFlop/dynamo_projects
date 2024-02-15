import os
import math

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("RevitNodes")
clr.AddReference('RevitServices')
import Autodesk.Revit.DB as DB # noqa
import Autodesk.Revit.UI as UI # noqa
import Autodesk.Revit.UI.Events.DialogBoxShowingEventArgs as DialogBoxShowingEventArgs # noqa
import Revit # noqa
clr.ImportExtensions(Revit.Elements)
clr.ImportExtensions(Revit.GeometryConversion)
import RevitServices.Persistence.DocumentManager as DocumentManager # noqa
import System.EventHandler as EventHandler # noqa


FEC = DB.FilteredElementCollector

MESSAGE_TRANSACTION_DELETE_FAM = 'DYNAMO Удаление старого семейства'
MESSAGE_TRANSACTION_CUT_VOID_ELT = (
    'DYNAMO Создание полого элемента лестницы,'
    ' и прорезание всех пересекающихся элементов'
)
CREATE_FAMILY_NAME = 'CutGeometryElements'
PATH_TEMPLATE_FAMITLY_TYPE_MODEL = (
    os.path.join(
        os.path.dirname(IN[0]), 'Метрическая система, типовая модель.rft' # noqa
    )
)
BINPAR_WORKSET = DB.BuiltInParameter.ELEM_PARTITION_PARAM
SHOW_DIALOG_ID = 'Dialog_Revit_DocWarnDialog'

UIAPP = DocumentManager.Instance.CurrentUIApplication
DOC = DocumentManager.Instance.CurrentDBDocument
APP = UIAPP.Application
UIDOC = UIAPP.ActiveUIDocument

G_OPTIONS = DB.Options()
G_OPTIONS.DetailLevel = DB.ViewDetailLevel.Fine


class SelectException(Exception):
    pass


def event_close_dialog_box(sender, args):
    '''Закрытие диалогового окна'''
    if args.DialogId == SHOW_DIALOG_ID:
        args.OverrideResult(int(UI.TaskDialogResult.Cancel))


def deco_events(func):
    '''
    Функция декоратор, закрытие диалогового окна,
    возникающего из-за привязки размеров к геометрии лестниц.
    Происходит подписка и отписка от события message box.
    '''
    def wrapper(*args, **kwargs):
        event_handler = (
            EventHandler[DialogBoxShowingEventArgs](event_close_dialog_box)
        )
        UIAPP.DialogBoxShowing += event_handler
        result = func(*args, **kwargs)
        UIAPP.DialogBoxShowing -= event_handler
        return result
    return wrapper


def get_select_stairs():
    select_element = [
        stair for stair in FEC(DOC).OfClass(DB.Architecture.Stairs)
    ]
    if not select_element:
        except_message = 'В проекте не найдено ни одной лестницы!'
        raise SelectException(except_message)
    return select_element


def get_all_solids_for_element(
        document, geometry_element):
    '''
    Получение всех солидов в геометрическом элементе
    Переменные:
    document: DB.Document
    geometry_element: DB.GeometryElement
    Возвращаемое значение: List[DB.Solid]
    '''
    solid_list = []
    for g_obgect in geometry_element:
        result = g_obgect
        if isinstance(result, DB.GeometryInstance):
            result = get_all_solids_for_element(
                document,
                result.SymbolGeometry
            )
            solid_list += result
        else:
            solid_list.append(result)
    return solid_list


def union_two_solid(first_solid, second_solid):
    '''Объединение двух солидов'''
    return DB.BooleanOperationsUtils.ExecuteBooleanOperation(
        first_solid, second_solid, DB.BooleanOperationsType.Union
    )


def union_solids(solids):
    '''
    Объединение всех солидов
    Переменные:
    solids: DB.Solid
    Возвращаемое значение: DB.Solid
    '''
    union_solid = union_two_solid(solids[0], solids[1])
    if len(solids) > 2:
        for i in range(len(solids) - 2):
            try:
                union_solid = union_two_solid(
                    union_solid,
                    solids[i + 2])
            except Exception:
                continue
    return union_solid


def create_new_family_element(document, name_symbol):
    '''
    Создание семейства в документе
    Переменные:
    document: DB.Document
    name_symbol: str
    Возвращаемые значения: DB.FamilyInstance
    '''
    built_in_par = DB.BuiltInParameter.ALL_MODEL_TYPE_NAME
    symbol = [
        element for element in FEC(document).OfClass(DB.FamilySymbol)
        if name_symbol == element.Parameter[built_in_par].AsString()
    ][0]
    symbol.Activate()
    try:
        return document.Create.NewFamilyInstance(
            DB.XYZ(0, 0, 0), symbol, DB.Structure.StructuralType.NonStructural
        )
    except Exception:
        return None


def doc_get_and_cut_intersect_element(
        document,
        intersect_elmenets,
        void_element,
        filter_category_id):
    '''
    Получение и вырезание пересекающихся элементов
    Переменные:
    document: DB.Document
    intersect_elements: List[DB.Architecture.Stairs] лестницы,
    по ним идет поиск пересечений.
    void_element: DB.FamilyInstance Семейство с пустотельной геометрией,
    которое обрезает пересекающиеся элементы.
    filter_category_id: DB.ElementId(DB.Category) Айди игнорируемой категории
    '''
    elements = []
    for inter_element in intersect_elmenets:
        filter = DB.ElementIntersectsElementFilter(inter_element)
        elements += [
            element for element in FEC(document).WherePasses(filter)
        ]
    elements = [
        element for element in elements
        if element.Category.Id != DB.ElementId(filter_category_id)
    ]
    elements = set(elements)
    for element in elements:
        try:
            DB.InstanceVoidCutUtils.AddInstanceVoidCut(
                DOC, element, void_element
            )
        except Exception:
            continue


def create_free_form_elt(fam_doc, solids):
    '''
    Создание фри форм в документе семейства
    fam_doc: DB.Document
    solids: List[DB.Solid]
    Возвращаемое значение:
    DB.FreeFormElement
    '''
    free_form_list = []
    for solid in solids:
        free_form_list.append(DB.FreeFormElement.Create(fam_doc, solid))
    return free_form_list


def set_geom_stairs_type(document, stair_type):
    '''
    Изменение типа лестниц, для упрощения этой геометрии, т.к.
    Revit не вырезает сложную геометрию.
    '''
    run_type = document.GetElement(stair_type.RunType)
    landing_type = document.GetElement(stair_type.LandingType)

    heigth_stairs_run_par = run_type.Parameter[
        DB.BuiltInParameter.STAIRS_RUNTYPE_STRUCTURAL_DEPTH]
    heigth_stairs_langing_par = landing_type.Parameter[
        DB.BuiltInParameter.STAIRS_LANDINGTYPE_THICKNESS]
    land_par = (
        DB.BuiltInParameter.STAIRS_LANDINGTYPE_USE_SAME_TRISER_AS_RUN)
    land_tread = DB.BuiltInParameter.STAIRS_TRISERTYPE_TREAD
    land_tread_thickness = (
        DB.BuiltInParameter.STAIRS_TRISERTYPE_TREAD_THICKNESS)

    if run_type.HasTreads:
        t_thickness = run_type.TreadThickness
        if run_type.HasRisers:
            r_thickness = run_type.RiserThickness
            heigth = math.sqrt(
                r_thickness**2 + t_thickness**2)
            heigth += heigth_stairs_run_par.AsDouble()
            heigth_stairs_run_par.Set(heigth)
            run_type.HasTreads = False
            run_type.HasRisers = False
        else:
            heigth = t_thickness
            heigth += heigth_stairs_run_par.AsDouble()
            heigth_stairs_run_par.Set(heigth)
            run_type.HasTreads = False
            if landing_type.Parameter[land_par].AsInteger():
                heigth_stairs_langing_par.Set(
                    t_thickness + heigth_stairs_langing_par.AsDouble())
            elif landing_type.Parameter[land_tread].AsInteger():
                heigth = (
                    landing_type.Parameter[land_tread_thickness].AsDouble() +
                    heigth_stairs_langing_par.AsDouble()
                )
                landing_type.Parameter[land_tread].Set(0)
                heigth_stairs_langing_par.Set(
                    heigth
                )

    return stair_type


def copy_type(el_type, suffix):
    '''
    Создание нового типа семейства на основе существующего
    el_type: DB.ElementType
    suffix: str
    Возвращаемое значение: new DB.ElementType
    '''
    par_name = DB.BuiltInParameter.ALL_MODEL_TYPE_NAME
    return el_type.Duplicate(
        el_type.Parameter[par_name].AsString() + '_{}'.format(suffix)
    )


@deco_events
def create_void_element(
        application, document, stairs, filter_category_id):
    '''
    Создание пустотельного семейства в документе
    Переменные:
    application: __revit__.Application
    document: DB.Document
    stairs: List[DB.Architecture.Stairs]
    filter_category_id: DB.ElementId(DB.Category)
    '''
    solids = []

    family_doc = application.NewFamilyDocument(
        PATH_TEMPLATE_FAMITLY_TYPE_MODEL
    )

    with DB.Transaction(document, 'Get all geometry') as t:
        t.Start()
        types_elt = {el.GetTypeId() for el in stairs}
        for type_el in types_elt:
            el_type = document.GetElement(type_el)
            set_geom_stairs_type(
                document, el_type
            )

        document.Regenerate()

        solids = []
        for element in stairs:
            solid = get_all_solids_for_element(
                DOC, element.Geometry[G_OPTIONS]
            )
            solids += solid
        solid = union_solids(solids)
        t.RollBack()

    with DB.Transaction(family_doc, 'Test') as t:
        t.Start()
        list_forms = create_free_form_elt(
            family_doc, [solid]
        )

        family_doc.Regenerate()

        built_in_par = DB.BuiltInParameter.ELEMENT_IS_CUTTING
        for form in list_forms:
            form.Parameter[built_in_par].Set(1)

        family_doc.Regenerate()

        family_doc.FamilyManager.NewType(CREATE_FAMILY_NAME)
        family_doc.OwnerFamily.Parameter[
            DB.BuiltInParameter.FAMILY_ALLOW_CUT_WITH_VOIDS].Set(1)
        fam = family_doc.LoadFamily(document)
        t.Commit()

    with DB.Transaction(document, MESSAGE_TRANSACTION_CUT_VOID_ELT) as t:
        t.Start()
        delete_family = [
            family for family in FEC(document).OfClass(DB.Family)
            if family.Name == CREATE_FAMILY_NAME
        ]
        if delete_family:
            document.Delete(delete_family[0])

        document.Regenerate()

        fam.Name = CREATE_FAMILY_NAME

        document.Regenerate()

        void_element = create_new_family_element(
            document, CREATE_FAMILY_NAME)

        if document.IsWorkshared:
            void_element.Parameter[BINPAR_WORKSET].Set(
                stairs[0].Parameter[BINPAR_WORKSET].AsInteger())

        document.Regenerate()

        doc_get_and_cut_intersect_element(
            document, stairs, void_element, filter_category_id
        )
        t.Commit()
    family_doc.Close(False)


stairs = get_select_stairs()

with DB.Transaction(DOC, MESSAGE_TRANSACTION_DELETE_FAM) as t:
    t.Start()
    delete_family = [
        family for family in FEC(DOC).OfClass(DB.Family)
        if family.Name == CREATE_FAMILY_NAME
    ]
    if delete_family:
        DOC.Delete(delete_family[0].Id)
    t.Commit()


create_void_element(APP, DOC, stairs, IN[1].Id) # noqa
OUT = 'Все готово'
