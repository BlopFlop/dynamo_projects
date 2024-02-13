import os

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB import FilteredElementCollector as FEC
clr.AddReference('RevitServices')
from RevitServices.Persistence import DocumentManager


PATHNAME_ANNOTAITIONS = '0021_ТаблицаИзменений_'
PAR_NUMBER_CHANGE = '01_1_№ Изм'
PAR_COUNT_CHANGE = '01_2_Кол-во измов/-'
PAR_SH_NUM = DB.BuiltInParameter.SHEET_NUMBER

user_docs = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Documents')

uiapp = DocumentManager.Instance.CurrentUIApplication
doc = DocumentManager.Instance.CurrentDBDocument
uidoc = uiapp.ActiveUIDocument


def bprint(array='', depth=0):
    '''Функция beautiful print
    Вывод в консоль массива данных построчно.
    Так же поддерживается рекурсивный вывод словарей

    Пример:
    d = {
        1: 10,
        2: [
            [200, 201],
            [210, 211],
            [220, 221]
        ],
        3: {
            30: {
                300: [301, 302, 303],
                310: [311, 312, 313]
            },
            31: [310, 320, 330]
        }
    }
    '''
    start_symbol = '\t' * depth
    if isinstance(array, dict):
        for key, value in array.items():
            bprint(key, depth)
            bprint(value, depth + 1)
    elif hasattr(array, '__iter__') and not isinstance(array, str):
        for element in array:
            bprint(element, depth)
    else:
        print('{}{}'.format(start_symbol, array))


def sorted_value_clouds(items):
    result_list = []
    sort_dict = {
        fst_val: {} for fst_val, scnd_val, result in items
    }
    for fst_val, scnd_val, result in items:
        if fst_val:
            sort_dict[fst_val][scnd_val] = result
        else:
            result_list.append(result)

    fst_sort_key = sorted(
        [int(value) for value in sort_dict.keys()]
    )

    for key in fst_sort_key:
        scnd_dict = sort_dict.get(str(key))
        scnd_sort_keys = sorted(
            [int(value) for value in scnd_dict.keys()]
        )
        for scnd_key in scnd_sort_keys:
            result_list.append(scnd_dict.get(str(scnd_key)))
    return result_list


def create_csv_analysis_file(data):
    file = open(
        os.path.join(user_docs, 'DYNAMO_AnalysisSheet.csv'),
        'w+',
    )
    file.write('\n\n'.join(data))
    file.close()


def check_select_sheet(select_elements):
    if not select_elements:
        raise Exception("Вы не выбрали ни одного листа.")


def check_value_par_in_sheet(select_element, name_parameter):
    if select_element:
        if not select_element[0].LookupParameter(name_parameter):
            raise Exception(
                'Параметр: << {} >> не обнаружен в листе.'.format(
                    name_parameter
                )
            )


def annotation_in_doc(document, name_family_annotation):
    '''Поиск аннотаций во всем документе'''
    result = []
    collector = (
        FEC(document).OfCategoryId(
            DB.ElementId(-2000150)).WhereElementIsNotElementType()
    )
    for elt in collector:
        value_par_name_fam = elt.AnnotationSymbolType.FamilyName
        check_annotation_obj = (
            isinstance(elt, DB.AnnotationSymbol) and (
                name_family_annotation == value_par_name_fam or
                name_family_annotation in value_par_name_fam
            )
        )
        if check_annotation_obj:
            result.append(elt)
    return result


def get_value_par_type_annotate(el, name_par):
    return doc.GetElement(el.GetTypeId()).LookupParameter(name_par).AsString()


class Sheet:
    '''Класс листа'''
    PAR_NUM_REVIS = DB.BuiltInParameter.REVISION_CLOUD_REVISION_NUM
    PAR_MODEL_MARK = DB.BuiltInParameter.ALL_MODEL_MARK
    PAR_INST_COMMENT = DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS

    def __init__(self, sheet, annotaions, revision_clouds):
        self.sheet = sheet
        self.annotaions = [
            annotate for annotate in annotaions
            if self.check_element_in_sheet(annotate)
        ]
        self.clouds = [
            cloud for cloud in revision_clouds
            if self.check_element_in_sheet(cloud)
        ]
        self.group_annotations = self.get_group_annotations()

        self.group_clouds = self.get_group_clouds()

    def clean_par_sheet(self, name_parameter_sheet):
        '''Отчистка параметра '''
        self.sheet.LookupParameter(name_parameter_sheet).Set('')

    def check_element_in_sheet(self, element):
        '''Проверка наличия элементов на листе'''
        if element.OwnerViewId.IntegerValue == self.sheet.Id.IntegerValue:
            return True
        return False

    def get_group_annotations(self):
        '''Группирование аннорации'''
        result = {
            get_value_par_type_annotate(annotate, PAR_NUMBER_CHANGE): []
            for annotate in self.annotaions
        }
        for annotate in self.annotaions:
            value_parameter = (
                get_value_par_type_annotate(annotate, PAR_NUMBER_CHANGE)
            )
            result[value_parameter].append(annotate)
        return result

    def get_group_clouds(self):
        '''Группирование облаков'''
        result = {
            cloud.Parameter[self.PAR_NUM_REVIS].AsString(): []
            for cloud in self.clouds
        }
        for cloud in self.clouds:
            value_parameter = cloud.Parameter[self.PAR_NUM_REVIS].AsString()
            result[value_parameter].append(cloud)
        return result

    def set_par_num_cloud(self):
        '''Добавление количества измов в облако'''
        for key in self.group_annotations.keys():
            clouds = self.group_clouds.get(key)
            annotations = self.group_annotations.get(key)
            if clouds:
                for annotate in annotations:
                    annotate.LookupParameter(PAR_COUNT_CHANGE).Set(
                        str(len(clouds))
                    )

    def set_par_sheet(self, name_par_comment_sheet):
        '''Изменнеие параметра листа'''
        list_num_clouds = []

        for key in self.group_clouds.keys():
            for clouds in self.group_clouds.get(key):
                clouds_par_number = (
                    clouds.Parameter[self.PAR_NUM_REVIS].AsString()
                )
                clouds_par_mark = (
                    clouds.Parameter[self.PAR_MODEL_MARK].AsString()
                )
                clouds_par_comments = (
                    clouds.Parameter[self.PAR_INST_COMMENT].AsString()
                )
                if clouds_par_comments and clouds_par_mark:
                    value = '{}.{} {}'.format(
                        clouds_par_number,
                        clouds_par_mark,
                        clouds_par_comments
                    )
                    list_num_clouds.append(
                        [clouds_par_number, clouds_par_mark, value]
                    )
                else:
                    list_num_clouds.append([0, 0, clouds_par_comments])

        bprint(sorted_value_clouds(list_num_clouds))

        self.sheet.LookupParameter(name_par_comment_sheet).Set(
            '\n\n'.join(sorted_value_clouds(list_num_clouds))
        )

    def __str__(self):
        return 'Лист, аннотации: {}, облака: {}.'.format(
            len(self.annotaions), len(self.clouds)
        )


def get_data_analysis(select_element):
    '''Получение информации о аннотациях размещенных на листах'''
    select_sheet_ids = [sheet.Id.IntegerValue for sheet in select_element]
    annotaions = annotation_in_doc(doc, PATHNAME_ANNOTAITIONS)
    sheet_in_annotation = {
        annotate.OwnerViewId.IntegerValue: [] for annotate in annotaions
    }
    for annotate in annotaions:
        sheet_in_annotation[annotate.OwnerViewId.IntegerValue].append(
            annotate.AnnotationSymbolType.FamilyName
        )

    result = []
    for sheet_id, annotate_fam_name in sheet_in_annotation.items():
        if sheet_id in select_sheet_ids:
            sheet = doc.GetElement(DB.ElementId(sheet_id))
            name_sheet = sheet.Parameter[PAR_SH_NUM].AsString()
            annotations_name = ', '.join(list(set(annotate_fam_name)))
            result.append(';'.join([name_sheet, annotations_name]))
    return sorted(result)


name_family = IN[0]
name_parameter_sheet_for_comments = IN[1]
data_analysis = IN[2]

select_element = [
    doc.GetElement(element_id)
    for element_id in uidoc.Selection.GetElementIds()
    if isinstance(doc.GetElement(element_id), DB.ViewSheet)
]

check_select_sheet(select_element)
check_value_par_in_sheet(select_element, name_parameter_sheet_for_comments)

annotaions = annotation_in_doc(doc, name_family)

revision_clouds = [cloud for cloud in FEC(doc).OfClass(DB.RevisionCloud)]

sheets = [
    Sheet(sheet, annotaions, revision_clouds) for sheet in select_element
]


with DB.Transaction(doc, 'DYNAMO Подсчет измов.') as t:
    t.Start()
    for sheet in sheets:
        sheet.clean_par_sheet(name_parameter_sheet_for_comments)
        if sheet.annotaions and sheet.clouds:
            sheet.set_par_num_cloud()
            sheet.set_par_sheet(name_parameter_sheet_for_comments)
    t.Commit()


if data_analysis:
    OUT = get_data_analysis(select_element)
else:
    OUT = ['Анализ не произведен']
