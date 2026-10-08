// A multi-line text field: the TextField frame, at least 72 px, growing with its
// text up to maxHeight and scrolling after that. Same label, error and states as TextField.
//   C.TextArea { label: "Vocet types"; text: draft.text }
// In a C.Sheet, Ctrl+Enter confirms (Enter adds a line). Tab / Shift+Tab move the focus on;
// Ctrl+Tab types a tab character.
import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import "." as C

FocusScope {
    id: field
    property alias text: area.text
    property alias placeholderText: area.placeholderText
    property alias readOnly: area.readOnly
    property alias input: area
    property string label: ""
    property string accessibleName: label !== "" ? label : area.placeholderText
    property string error: ""
    property real minHeight: 72
    property real maxHeight: 160
    property string demoState: ""

    readonly property bool hasError: error !== ""
    readonly property bool isHovered: demoState === "hover" || hover.hovered
    readonly property bool isFocused: demoState === "focus" || area.activeFocus
    readonly property real hairline: 1 / Screen.devicePixelRatio

    implicitWidth: 320
    implicitHeight: column.implicitHeight
    onErrorChanged: if (error !== "") errorRow.Accessible.announce(error)

    ColumnLayout {
        id: column
        width: parent.width
        spacing: 0

        C.Txt {
            visible: field.label !== ""
            text: field.label
            textStyle: "footnote"
            tone: field.enabled ? "secondary" : "disabled"
            Layout.fillWidth: true
            Layout.bottomMargin: theme.space2
            Accessible.ignored: true
        }

        Item {
            id: box
            Layout.fillWidth: true
            implicitHeight: Math.min(field.maxHeight, Math.max(field.minHeight, area.implicitHeight))

            C.Glass { anchors.fill: parent; kind: "field"; radius: theme.radiusField; opacity: field.enabled ? 1 : 0.6 }
            C.Fill {
                anchors.fill: parent
                radius: theme.radiusField
                hovered: field.isHovered
                tint: field.isHovered && field.enabled && !field.isFocused ? theme.fillHover : Qt.alpha(theme.fillHover, 0)
            }
            Rectangle {  // an error, or a contrast theme: a real outline
                anchors.fill: parent
                visible: field.hasError || theme.highContrast
                radius: theme.radiusField
                color: "transparent"
                border.width: 1
                border.color: field.hasError ? theme.dangerText : theme.strokeStrong
            }
            C.FocusRing { show: field.isFocused; error: field.hasError; controlRadius: theme.radiusField }
            HoverHandler { id: hover; cursorShape: Qt.IBeamCursor }

            Flickable {
                id: flick
                anchors.fill: parent
                anchors.bottomMargin: 1
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                acceptedButtons: Qt.NoButton
                contentWidth: width
                contentHeight: area.implicitHeight
                T.ScrollBar.vertical: C.ScrollBar {}

                T.TextArea.flickable: T.TextArea {
                    id: area
                    focus: true
                    padding: 10
                    topPadding: 8
                    bottomPadding: 8
                    wrapMode: TextEdit.Wrap
                    font.family: theme.bodyFamily
                    font.pixelSize: theme.bodySize
                    font.weight: theme.bodyWeight
                    color: field.enabled ? theme.textPrimary : theme.textDisabled
                    selectionColor: theme.selection
                    selectedTextColor: theme.onSelection
                    placeholderTextColor: field.enabled ? theme.textTertiary : theme.textDisabled
                    selectByMouse: true
                    hoverEnabled: false
                    cursorDelegate: C.Caret {}
                    background: null
                    Accessible.name: field.accessibleName
                    Accessible.description: field.hasError ? field.error : ""
                    // Tab and Shift+Tab move the focus, as in every other field (a TextEdit would
                    // type a tab and trap the keyboard). Ctrl+Tab types a real tab, as in Windows'
                    // multi-line edit boxes.
                    Keys.onPressed: (event) => {
                        if (event.key !== Qt.Key_Tab && event.key !== Qt.Key_Backtab) return
                        event.accepted = true
                        if (event.modifiers & Qt.ControlModifier) {
                            if (event.key === Qt.Key_Tab && !(event.modifiers & Qt.ShiftModifier) && !area.readOnly) {
                                area.remove(area.selectionStart, area.selectionEnd)
                                area.insert(area.cursorPosition, "\t")
                            }
                            return
                        }
                        const forward = event.key === Qt.Key_Tab && !(event.modifiers & Qt.ShiftModifier)
                        const next = area.nextItemInFocusChain(forward)
                        if (next && next !== area)
                            next.forceActiveFocus(forward ? Qt.TabFocusReason : Qt.BacktabFocusReason)
                    }

                    C.Txt {  // starts 3 px after the text's own origin: the empty field's caret (2 px) sits before it, not over its first letter
                        x: area.leftPadding + 3
                        y: area.topPadding
                        width: area.width - area.leftPadding - area.rightPadding - 3
                        visible: area.text.length === 0 && area.preeditText.length === 0
                        text: area.placeholderText
                        textStyle: "body"
                        color: area.placeholderTextColor
                        wrapMode: Text.Wrap
                        Accessible.ignored: true
                    }
                }
            }
        }

        RowLayout {
            id: errorRow
            visible: field.hasError
            Layout.fillWidth: true
            Layout.topMargin: theme.space2
            spacing: 6
            Accessible.role: Accessible.AlertMessage
            Accessible.name: field.error
            C.Icon { name: "warning"; size: 12; color: theme.dangerText; Layout.alignment: Qt.AlignTop; Layout.topMargin: 2 }
            C.Txt {
                text: field.error
                textStyle: "footnote"
                tone: "danger"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                Accessible.ignored: true
            }
        }
    }
}
