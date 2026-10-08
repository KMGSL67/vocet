// A confirmation dialog, for irreversible, uncommon actions only (Clear history…);
// never for an undoable delete. 400 px, padding 24, radius 12, level 2, scrim behind.
// title3 title, body textSecondary message, 24 px, then the buttons right-aligned in Windows
// order: [confirm] [Cancel]. Initial focus on Cancel, no default button, Esc cancels, and Tab
// stays inside (modal); closing gives the focus back to what opened it. Motion: scrim 150 ms; panel opacity 150 ms + scale 0.97 → 1 over
// 200 ms OutCubic; close: opacity 120 ms InCubic.
//   C.ConfirmDialog {
//       id: confirmClear
//       title: "Delete all dictations?"
//       message: "This removes every dictation saved on this PC. You can't undo this."
//       confirmText: "Delete all"; destructive: true
//       onConfirmed: backend.clearHistory()
//   }
//   … confirmClear.open()
import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import "." as C

T.Popup {
    id: root
    property string title: ""
    property string message: ""
    property string confirmText: "OK"
    property string cancelText: "Cancel"
    property bool destructive: false
    signal confirmed()
    signal cancelled()

    parent: T.Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    closePolicy: T.Popup.CloseOnEscape
    width: Math.min(400, parent ? parent.width - 48 : 400)
    padding: theme.space7
    // Templates give popups no implicit size: take it from the content, as the Qt styles do.
    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset, contentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset, contentHeight + topPadding + bottomPadding)
    onOpened: cancelButton.forceActiveFocus(Qt.OtherFocusReason)
    onClosed: {
        Qt.callLater(_giveBackFocus)      // after the popup's own focus hand-back, which would win
        if (!_confirming) cancelled()
    }
    function _giveBackFocus() {           // to what opened the dialog, ring and all
        if (visible) return
        const reason = _openerRing ? Qt.TabFocusReason : Qt.OtherFocusReason
        if (_opener && _opener.visible && _opener.enabled) {
            _opener.forceActiveFocus(reason)
            if (_opener.focusReason !== undefined) _opener.focusReason = reason   // it may have it already, without its ring
        }
        _opener = null
    }
    property bool _confirming: false
    property Item _opener: null
    property bool _openerRing: false
    onAboutToShow: {
        _confirming = false
        _opener = parent ? parent.Window.activeFocusItem : null
        _openerRing = !!(_opener && _opener.visualFocus)
    }

    T.Overlay.modal: Rectangle { color: theme.scrim }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: backend.reducedMotion ? theme.motionFast : theme.motionBase; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: backend.reducedMotion ? 1 : 0.97; to: 1; duration: theme.motionMedium; easing.type: Easing.OutCubic }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; to: 0; duration: backend.reducedMotion ? theme.motionFast : 120; easing.type: Easing.InCubic }
    }

    background: C.Surface { level: 2; radius: theme.radiusDialog }

    contentItem: ColumnLayout {
        spacing: 0
        Accessible.role: Accessible.Dialog
        Accessible.name: root.title
        Accessible.description: root.message
        C.Txt {
            text: root.title
            textStyle: "title3"
            heading: true
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        C.Txt {
            visible: root.message !== ""
            text: root.message
            textStyle: "body"
            tone: "secondary"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            Layout.topMargin: theme.space3
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: theme.space7
            spacing: theme.space3
            Item { Layout.fillWidth: true }
            C.Button {
                id: confirmButton
                text: root.confirmText
                kind: root.destructive ? "destructive" : "primary"
                filled: root.destructive
                dialog: true
                KeyNavigation.tab: cancelButton
                KeyNavigation.backtab: cancelButton
                onClicked: {
                    root._confirming = true
                    root.close()
                    root.confirmed()
                }
            }
            C.Button {
                id: cancelButton
                text: root.cancelText
                dialog: true
                KeyNavigation.tab: confirmButton
                KeyNavigation.backtab: confirmButton
                onClicked: root.close()
            }
        }
    }
}
