// A pop-up button (design v4), for flat lists of mutually exclusive choices with a sensible
// default (shortcut, microphone, history retention). A 34 px glass capsule like a secondary
// button, 120–280 px wide; label 16 px from the left, 12 px chevron 14 px from the right.
// Hover controlHover; pressed or open controlPressed; focus ring.
// The menu opens with the current item over the label (like macOS and the WinUI ComboBox),
// stays inside the window and scrolls past 320 px: level-1 surface, 4 px padding, 32 px items
// with a 24 px checkmark column; the current item carries a checkmark. Keys: ↑/↓, Enter, Esc,
// type to select.
//   C.PopUpButton {
//       label: "Shortcut"                     // accessible name (a SettingRow fills it in)
//       model: backend.hotkeys; textRole: "label"; valueRole: "key"
//       value: backend.settings.hotkey
//       onPicked: (v) => backend.setSetting("hotkey", v)
//   }
import QtQuick
import QtQuick.Templates as T
import "." as C

T.ComboBox {
    id: box
    property string label: ""
    property var value
    property string demoState: ""      // gallery only: "hover" | "pressed" | "focus"
    signal picked(var value)
    function openMenu() { popup.open() }   // scripts (render_window.py --open)

    readonly property bool isHovered: demoState === "hover" || hovered
    readonly property bool isPressed: demoState === "pressed" || down || (popup && popup.visible)
    readonly property bool isFocused: demoState === "focus" || visualFocus
    readonly property int itemHeight: Math.max(34, theme.bodyLine + 14)
    readonly property real hairline: 1 / Screen.devicePixelRatio

    // Fits the widest choice (120–280 px). ComboBox.WidestText only measures a TextInput
    // content item, so the labels are measured here.
    property real widestText: 0
    function measure() {
        let w = 0
        for (let i = 0; i < measures.count; i++) {
            const t = measures.itemAt(i)
            if (t) w = Math.max(w, t.implicitWidth)
        }
        widestText = Math.ceil(w)
    }
    Repeater {
        id: measures
        model: box.count
        C.Txt {
            required property int index
            visible: false
            text: box.textAt(index)
            textStyle: "body"
            onImplicitWidthChanged: box.measure()
        }
        onCountChanged: box.measure()
    }

    textRole: "label"
    valueRole: "key"
    currentIndex: { box.count; return box.value === undefined ? -1 : box.indexOfValue(box.value) }
    implicitWidth: Math.max(120, Math.min(280, widestText + leftPadding + rightPadding))
    implicitHeight: itemHeight
    leftPadding: 16
    rightPadding: 34
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: label
    onActivated: (index) => box.picked(box.valueAt(index))

    background: Item {
        C.Glass { anchors.fill: parent; kind: "control"; radius: height / 2 }
        C.Fill {
            anchors.fill: parent
            radius: height / 2
            hovered: box.isHovered
            pressed: box.isPressed
            tint: !box.enabled ? Qt.alpha(theme.controlHover, 0)
                : box.isPressed ? theme.controlPressed
                : box.isHovered ? theme.controlHover : Qt.alpha(theme.controlHover, 0)
            border.width: theme.highContrast ? 1 : 0
            border.color: theme.strokeStrong
        }
        C.FocusRing { show: box.isFocused; controlRadius: height / 2 }
    }

    contentItem: C.Txt {
        id: display
        text: box.displayText
        textStyle: "body"
        tone: box.enabled ? "primary" : "disabled"
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        Accessible.ignored: true
    }

    // The closed control can be narrower than its label (e.g. every pop-up on Settings is one
    // width): a truncated choice still needs its full name somewhere.
    C.Tooltip {
        text: box.displayText
        visible: display.truncated && (box.isHovered || box.isFocused)
    }

    indicator: C.Icon {
        x: box.width - 14 - width
        y: Math.round((box.height - height) / 2)
        name: "chevronDown"
        size: 12
        color: box.enabled ? theme.textSecondary : theme.textDisabled
    }

    delegate: T.ItemDelegate {
        id: option
        required property var model
        required property int index
        readonly property string itemText: Array.isArray(box.model) ? model.modelData[box.textRole] : model[box.textRole]
        width: ListView.view ? ListView.view.width : implicitWidth
        implicitHeight: box.itemHeight
        leftPadding: 28
        rightPadding: 12
        hoverEnabled: true
        highlighted: box.highlightedIndex === index
        Accessible.role: Accessible.ListItem
        Accessible.name: itemText
        Accessible.selected: box.currentIndex === index
        contentItem: C.Txt {
            text: option.itemText
            textStyle: "body"
            tone: option.enabled ? "primary" : "disabled"
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            Accessible.ignored: true
        }
        indicator: C.Icon {
            x: 6
            y: Math.round((option.height - height) / 2)
            name: "checkmark"
            size: 12
            color: theme.accentText
            visible: box.currentIndex === option.index
        }
        background: Rectangle {
            radius: theme.radiusMenuItem
            color: option.highlighted ? theme.fillHover : Qt.alpha(theme.fillHover, 0)
        }
    }

    popup: T.Popup {
        id: menu
        readonly property real listHeight: box.count * box.itemHeight
        readonly property bool fits: listHeight + 8 <= 320
        x: -20
        y: fits ? -(4 + Math.max(0, box.currentIndex) * box.itemHeight) : box.height + 4
        width: Math.max(box.width + 20, Math.min(360, box.widestText + 48))
        height: Math.min(320, listHeight + 8)
        padding: 0
        margins: 8
        onOpened: list.positionViewAtIndex(Math.max(0, box.currentIndex), ListView.Contain)

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: backend.reducedMotion ? 0 : 120; easing.type: Easing.OutCubic }
            NumberAnimation { target: shift; property: "y"; from: backend.reducedMotion ? 0 : -4; to: 0; duration: 120; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; to: 0; duration: backend.reducedMotion ? 0 : 80; easing.type: Easing.InCubic }
        }
        contentItem: Item {
            transform: Translate { id: shift }
            C.Surface { anchors.fill: parent; level: 1; radius: theme.radiusMenu }
            ListView {
                id: list
                anchors.fill: parent
                anchors.margins: 4
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: menu.visible ? box.delegateModel : null
                currentIndex: box.highlightedIndex
                highlightMoveDuration: 0
                T.ScrollBar.vertical: C.ScrollBar {}
            }
        }
        background: null
    }
}
