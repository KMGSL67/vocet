// The keyboard focus ring: 2 px wide with a 2 px gap, radius = the control's + 4.
// theme.focus (the accent's ring colour). Appears instantly. Put it inside a control's background
// and bind `show` to the control's visualFocus (keyboard focus only). Fields use activeFocus.
//   C.FocusRing { show: control.visualFocus; controlRadius: theme.radiusControl }
import QtQuick

Rectangle {
    property bool show: false
    property real controlRadius: theme.radiusControl
    property bool error: false
    anchors.fill: parent
    anchors.margins: -4
    radius: controlRadius + 4
    color: "transparent"
    border.width: 2
    border.color: error ? theme.dangerText : theme.focus
    antialiasing: true
    visible: show
}
