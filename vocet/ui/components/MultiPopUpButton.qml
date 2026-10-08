// A pop-up button for choosing several things at once (design v4), e.g. "Languages you speak".
// Closed, it looks exactly like PopUpButton (34 px glass capsule, label 16 px from the left, 12 px
// chevron 14 px from the right) and its label sums up the choice: "English, Deutsch, Français".
// Its menu is PopUpButton's too (level-1 surface, 4 px padding, items with a 24 px checkmark
// column), opened below the button, and it stays open while you tick and untick. An item may add
// a quieter detail ("Chinese") and a badge ("Beta"). `minimum` items stay chosen: the last one
// can't be unticked, so it shows dimmed. Keys: Space, Enter, ↓ or ↑ open; in the menu ↑/↓ move,
// Space/Enter tick, Esc or Tab close.
//   C.MultiPopUpButton {
//       label: "Languages you speak"          // accessible name (a SettingRow fills it in)
//       model: backend.spokenLanguages        // [{ key, label, detail, badge }]
//       values: backend.settings.languages    // the chosen keys
//       onPicked: (values) => backend.setSetting("languages", values)   // in the model's order
//   }
import QtQuick
import QtQuick.Templates as T
import "." as C

T.AbstractButton {
    id: box
    property string label: ""
    property var model: []
    property var values: []
    property string textRole: "label"
    property string valueRole: "key"
    property string detailRole: "detail"
    property string badgeRole: "badge"
    property int minimum: 1
    property string demoState: ""      // gallery only: "hover" | "pressed" | "focus" | "open"
    signal picked(var values)

    readonly property bool isOpen: menu.visible
    readonly property bool isHovered: demoState === "hover" || hovered
    readonly property bool isPressed: demoState === "pressed" || down || isOpen
    readonly property bool isFocused: demoState === "focus" || visualFocus
    readonly property int itemHeight: Math.max(34, theme.bodyLine + 14)
    readonly property int count: model ? model.length : 0

    function chosen(v) { return (values || []).indexOf(v) >= 0 }
    function locked(v) { return chosen(v) && (values || []).length <= minimum }
    readonly property string summary: {
        const names = []
        for (let i = 0; i < count; i++)
            if (chosen(model[i][valueRole])) names.push(model[i][textRole])
        return names.join(", ")
    }
    function toggle(index) {
        if (index < 0 || index >= count) return
        const v = model[index][valueRole]
        if (locked(v)) return
        const next = []
        for (let i = 0; i < count; i++) {
            const k = model[i][valueRole]
            if (k === v ? !chosen(v) : chosen(k)) next.push(k)
        }
        picked(next)
    }
    function open() { menu.open() }

    // Fits the widest item (label + detail + badge) so the menu never truncates one.
    property real widestItem: 0
    function measure() {
        let w = 0
        for (let i = 0; i < measures.count; i++) {
            const t = measures.itemAt(i)
            if (t) w = Math.max(w, t.implicitWidth)
        }
        widestItem = Math.ceil(w)
    }
    Repeater {
        id: measures
        model: box.count
        Row {
            required property int index
            visible: false
            spacing: 8
            C.Txt { text: box.model[index][box.textRole]; textStyle: "body" }
            C.Txt { text: box.model[index][box.detailRole] || ""; textStyle: "subheadline" }
            C.Badge { text: box.model[index][box.badgeRole] || ""; visible: text !== "" }
            onImplicitWidthChanged: box.measure()
        }
        onCountChanged: box.measure()
    }

    implicitWidth: Math.max(120, Math.min(280, display.implicitWidth + leftPadding + rightPadding))
    implicitHeight: itemHeight
    leftPadding: 16
    rightPadding: 34
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.ComboBox
    Accessible.name: label
    Accessible.description: summary
    onClicked: menu.open()
    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Down
                || event.key === Qt.Key_Up) {
            menu.open()
            event.accepted = true
        }
    }

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
        text: box.summary
        textStyle: "body"
        tone: box.enabled ? "primary" : "disabled"
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        Accessible.ignored: true
    }

    // Every pop-up on Settings is one width: a summary that doesn't fit still shows in full here.
    C.Tooltip {
        text: box.summary
        visible: display.truncated && (box.isHovered || box.isFocused) && !box.isOpen
    }

    indicator: C.Icon {
        x: box.width - 14 - width
        y: Math.round((box.height - height) / 2)
        name: "chevronDown"
        size: 12
        color: box.enabled ? theme.textSecondary : theme.textDisabled
    }

    T.Popup {
        id: menu
        readonly property real listHeight: box.count * box.itemHeight
        x: -16                          // item labels line up with the button's label
        y: box.height + 4
        width: Math.max(box.width + 16, Math.min(360, box.widestItem + 48))
        height: Math.min(320, listHeight + 8)
        padding: 0
        margins: 8
        focus: true
        closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutsideParent
        onOpened: {
            let first = 0
            for (let i = 0; i < box.count; i++)
                if (box.chosen(box.model[i][box.valueRole])) { first = i; break }
            list.currentIndex = first
            list.positionViewAtIndex(first, ListView.Contain)
            list.forceActiveFocus()
        }
        onClosed: if (box.enabled) box.forceActiveFocus()

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
                model: menu.visible ? box.count : 0
                highlightMoveDuration: 0
                keyNavigationEnabled: true
                Accessible.role: Accessible.List
                Accessible.name: box.label
                T.ScrollBar.vertical: C.ScrollBar {}
                Keys.onPressed: (event) => {
                    if (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        box.toggle(list.currentIndex)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
                        menu.close()
                        event.accepted = true
                    }
                }

                delegate: T.ItemDelegate {
                    id: option
                    required property int index
                    readonly property var entry: box.model[index]
                    readonly property string key: entry[box.valueRole]
                    readonly property bool isChosen: box.chosen(key)
                    readonly property bool isLocked: box.locked(key)
                    readonly property string detail: entry[box.detailRole] || ""
                    readonly property string badge: entry[box.badgeRole] || ""
                    width: ListView.view ? ListView.view.width : implicitWidth
                    implicitHeight: box.itemHeight
                    leftPadding: 28
                    rightPadding: 12
                    hoverEnabled: true
                    focusPolicy: Qt.NoFocus
                    highlighted: ListView.isCurrentItem
                    onHoveredChanged: if (hovered) list.currentIndex = index
                    onClicked: { list.currentIndex = index; box.toggle(index) }
                    Accessible.role: Accessible.CheckBox
                    Accessible.checkable: true
                    Accessible.checked: isChosen
                    Accessible.name: entry[box.textRole] + (detail ? ", " + detail : "") + (badge ? ", " + badge : "")
                    Accessible.description: isLocked ? "At least one stays chosen." : ""
                    contentItem: Row {
                        spacing: 8
                        C.Txt {
                            anchors.verticalCenter: parent.verticalCenter
                            text: option.entry[box.textRole]
                            textStyle: "body"
                            tone: option.isLocked ? "secondary" : "primary"
                            Accessible.ignored: true
                        }
                        C.Txt {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: option.detail !== ""
                            text: option.detail
                            textStyle: "subheadline"
                            tone: "secondary"
                            Accessible.ignored: true
                        }
                        C.Badge {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: option.badge !== ""
                            text: option.badge
                            Accessible.ignored: true
                        }
                    }
                    indicator: C.Icon {
                        x: 6
                        y: Math.round((option.height - height) / 2)
                        name: "checkmark"
                        size: 12
                        color: option.isLocked ? theme.textSecondary : theme.accentText
                        visible: option.isChosen
                    }
                    background: Rectangle {
                        radius: theme.radiusMenuItem
                        color: option.highlighted ? theme.fillHover : Qt.alpha(theme.fillHover, 0)
                    }
                }
            }
        }
        background: null
    }
    Component.onCompleted: if (demoState === "open") menu.open()
}
