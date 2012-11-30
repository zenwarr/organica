from PyQt4.QtCore import QRect
from PyQt4.QtGui import QApplication

def rectangleCenter(rect, size):
	x = rect.left() + (rect.width() - size.width()) / 2
	y = rect.top() + (rect.height() - size.height()) / 2
	return QRect(x, y, size.width(), size.height())

def collapseRectangle(rect, amount):
	rc = rect

	ac = amount if rc.height() >= amount * 2 else rc.height() / 2
	rc.setTop(rc.top() + ac)
	rc.setBottom(rc.bottom() - ac)

	ac = amount if rc.width() >= amount * 2 else rc.width() / 2
	rc.setLeft(rc.left() + ac)
	rc.setRight(rc.right() - ac)

	return rc

def getRectangleForWindow(preferred, parent = None, minimal = None):
	"""
	Finds best possible window rectangle to fit on screen.
	If preferred size does not fit on screen it will be collapsed
	(but will not get smaller than minimal).
	If preferred size is too small, minimal will be returned.
	Note that function returns rectangle identifying frame size, not
	client area.
	"""

	if minimal is None:
		minimal = QSize(40, 30)

	if preferred.height() < minimal.height() and preferred.width() < minimal.width():
		return minimal

	desktop_widget = QApplication.instance().desktop()
	avail_rect = None
	parent_rect = None

	if parent is not None:
		parent_rect = QRect(parent.pos(), parent.size())
		avail_rect = desktop_widget.availableGeometry(parent)
	else:
		parent_rect = desktop_widget.availableGeometry()
		avail_rect = parent_rect

	rect = rectangleCenter(parent_rect, preferred)

	if rect.height() > avail_rect.height():
		height = max(avail_rect.height(), minimal.height())
		dc = (rect.height() - height) / 2
		rect.setTop(rect.top() + dc)
		rect.setBottom(rect.bottom() - dc)

	if rect.width() > avail_rect.width():
		width = max(avail_rect.width(), minimal.width())
		dc = (rect.width() - width) / 2
		rect.setLeft(rect.left() + dc)
		rect.setRight(rect.right() - dc)

	return rect
