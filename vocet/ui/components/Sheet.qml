// A sheet: a modal form such as New snippet / Edit snippet. 480 px, padding 24,
// radius 12, level 2, scrim behind. title3 title, then your fields (labelled, footnote labels
// above), then [primary] [Cancel] right-aligned. The primary is the default: Enter in a
// one-line field, Ctrl+Enter in a text area. Esc cancels. Tab stays inside. Closing gives the
// focus back to what opened it (or `returnFocus`).
// Closing doesn't clear anything: keep the draft in your fields for the session.
//   C.Sheet {
//       id: sheet
//       title: "New snippet"; primaryText: "Add snippet"
//       primaryEnabled: trigger.text.trim() !== "" && body.text.trim() !== ""
//       onAccepted: backend.addSnippet(trigger.text, body.text)
//       C.TextField { id: trigger; label: "When I say"; Layout.fillWidth: true }
//       C.TextArea { id: body; label: "Vocet types"; Layout.fillWidth: true }
//   }
import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import "." as C

T.Popup {
    id: sheet
    property string title: ""
    property string primaryText: "Save"
    property string cancelText: "Cancel"
    property bool primaryEnabled: true
    property Item initialFocus: null      // default: the first field
    default property alias content: fields.data
    signal accepted()
    signal cancelled()

    function accept() {
        if (!primaryEnabled) return
        _accepting = true
        close()
        accepted()
    }
    property bool _accepting: false
    // Closing gives the focus back: to returnFocus if set (an Item, or a
    // function returning one, for an opener that the change rebuilds), else to what had it
    // when the sheet opened; with its focus ring if that had one.
    property var returnFocus: null
    property Item _opener: null
    property bool _openerRing: false
    onAboutToShow: {
        _accepting = false
        _opener = parent ? parent.Window.activeFocusItem : null
        _openerRing = !!(_opener && _opener.visualFocus)
    }
    onClosed: {
        Qt.callLater(_giveBackFocus)      // after the popup's own focus hand-back, which would win
        if (!_accepting) cancelled()
    }
    function _giveBackFocus() {
        if (visible) return               // opened again meanwhile
        const back = typeof returnFocus === "function" ? returnFocus() : (returnFocus || _opener)
        const reason = _openerRing ? Qt.TabFocusReason : Qt.OtherFocusReason
        if (back && back.visible && back.enabled) {
            back.forceActiveFocus(reason)
            if (back.focusReason !== undefined) back.focusReason = reason   // it may have it already, without its ring
        }
        _opener = null
    }
    onOpened: {
        const first = initialFocus || (fields.children.length > 0 ? fields.children[0] : null)
        if (first) first.forceActiveFocus(Qt.OtherFocusReason)
    }

    parent: T.Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    closePolicy: T.Popup.CloseOnEscape
    width: Math.min(480, parent ? parent.width - 48 : 480)
    padding: theme.space7
    // Templates give popups no implicit size: take it from the content, as the Qt styles do.
    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset, contentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset, contentHeight + topPadding + bottomPadding)

    T.Overlay.modal: Rectangle { color: theme.scrim }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: backend.reducedMotion ? theme.motionFast : theme.motionBase; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: backend.reducedMotion ? 1 : 0.97; to: 1; duration: theme.motionMedium; easing.type: Easing.OutCubic }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; to: 0; duration: backend.reducedMotion ? theme.motionFast : 120; easing.type: Easing.InCubic }
    }

    background: C.Surface { level: 2; radius: theme.radiusDialog }

    Shortcut {
        sequences: ["Ctrl+Return", "Ctrl+Enter"]
        enabled: sheet.visible
        onActivated: sheet.accept()
    }

    contentItem: FocusScope {
        implicitHeight: column.implicitHeight
        implicitWidth: column.implicitWidth
        Accessible.role: Accessible.Dialog
        Accessible.name: sheet.title
        Keys.onReturnPressed: sheet.accept()
        Keys.onEnterPressed: sheet.accept()

        ColumnLayout {
            id: column
            width: parent.width
            spacing: 0
            C.Txt {
                text: sheet.title
                textStyle: "title3"
                heading: true
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            ColumnLayout {
                id: fields
                Layout.fillWidth: true
                Layout.topMargin: theme.space5
                spacing: theme.space4
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: theme.space7
                spacing: theme.space3
                Item { Layout.fillWidth: true }
                C.Button {
                    text: sheet.primaryText
                    kind: "primary"
                    dialog: true
                    enabled: sheet.primaryEnabled
                    onClicked: sheet.accept()
                }
                C.Button {
                    text: sheet.cancelText
                    dialog: true
                    onClicked: sheet.close()
                }
            }
        }
    }
}
