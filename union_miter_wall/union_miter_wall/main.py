import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit import DB # noqa
clr.AddReference('RevitServices')
from RevitServices.Persistence import DocumentManager # noqa


TRANSACTION_NAME = 'DYNAMO Соединение выбранных стен под углом.'

UIAPP = DocumentManager.Instance.CurrentUIApplication
DOC = DocumentManager.Instance.CurrentDBDocument
APP = UIAPP.Application
UIDOC = UIAPP.ActiveUIDocument


class SelectException(Exception):
    pass


def check_selection_element(select_el):
    except_message = 'Выберите хотя бы одну стену.'
    if not select_el:
        raise SelectException(except_message)


def set_miter_walls(walls):
    '''Mitter compound for walls'''
    with DB.Transaction(DOC, TRANSACTION_NAME) as t:
        t.Start()
        for wall in walls:
            location_curve = wall.Location
            location_curve.JoinType[1] = DB.JoinType.Miter
            location_curve.JoinType[0] = DB.JoinType.Miter
        t.Commit()


selection_wall = set_miter_walls([
    DOC.GetElement(el_id) for el_id in UIDOC.Selection.GetElementIds()
    if isinstance(DOC.GetElement(el_id), DB.Wall)
])

check_selection_element(selection_wall)

OUT = 'Соединено {}'.format(str(len(selection_wall)))
