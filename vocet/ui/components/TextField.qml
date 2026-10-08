// A text field (design v4): 34 px, radius 10 (a capsule with `capsule: true`), a flat glass
// well with an even rim (C.Glass kind "field"). Body text with 12 px padding (34 px on the
// leading side with an icon), placeholder in textTertiary, the 2 px textPrimary caret,
// `selection` behind selected text.
// States: hover fillHover + I-beam; focus ring (on any focus: a field shows where you type);
// disabled fillControl + textDisabled; error: dangerText bottom edge and ring plus a footnote
// message with a 12 px warning glyph, announced to screen readers.
//   C.TextField { label: "Often heard as"; placeholderText: "optional"; onAccepted: … }
// label: a visible footnote label above, for fields whose meaning is lost once you type.
// clearButton: an ✕ (12 px in a 24 × 24 target) while the field isn't empty.
import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import "." as C

FocusScope {
    id: field
    property alias text: input.text
    property alias placeholderText: input.placeholderText
    property alias readOnly: input.readOnly
    property alias maximumLength: input.maximumLength
    property alias validator: input.validator
    property alias input: input
    property string label: ""
    property string accessibleName: label !== "" ? label : input.placeholderText
    property string error: ""
    property string iconName: ""
    property bool clearButton: true
    property bool capsule: false       // the search field: a capsule, like the buttons
    readonly property real radius: capsule ? box.height / 2 : theme.radiusField
    property string demoState: ""      // gallery only: "hover" | "focus"
    signal accepted()
    signal cleared()

    readonly property bool hasError: error !== ""
    readonly property bool isHovered: demoState === "hover" || hover.hovered
    readonly property bool isFocused: demoState === "focus" || input.activeFocus
    readonly property bool showClear: clearButton && enabled && !input.readOnly && input.text.length > 0
    readonly property real hairline: 1 / Screen.devicePixelRatio

    function clear() {
        input.clear()
        cleared()
    }
    function selectAll() { input.selectAll() }

    implicitWidth: 240
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
            implicitHeight: Math.max(34, input.implicitHeight + 14)

            C.Glass { anchors.fill: parent; kind: "field"; radius: field.radius; opacity: field.enabled ? 1 : 0.6 }
            C.Fill {
                anchors.fill: parent
                radius: field.radius
                hovered: field.isHovered
                tint: field.isHovered && field.enabled && !field.isFocused ? theme.fillHover : Qt.alpha(theme.fillHover, 0)
            }
            Rectangle {  // an error, or a contrast theme: a real outline
                anchors.fill: parent
                visible: field.hasError || theme.highContrast
                radius: field.radius
                color: "transparent"
                border.width: 1
                border.color: field.hasError ? theme.dangerText : theme.strokeStrong
            }
            C.FocusRing { show: field.isFocused; error: field.hasError; controlRadius: field.radius }

            HoverHandler { id: hover; cursorShape: Qt.IBeamCursor }

            C.Icon {
                visible: field.iconName !== ""
                name: field.iconName
                size: 16
                x: field.capsule ? 14 : 10
                anchors.verticalCenter: parent.verticalCenter
                color: field.enabled ? theme.textSecondary : theme.textDisabled
            }

            T.TextField {
                id: input
                anchors.fill: parent
                focus: true
                leftPadding: field.iconName !== "" ? (field.capsule ? 38 : 34) : (field.capsule ? 16 : 12)
                rightPadding: field.showClear ? 32 : (field.capsule ? 16 : 12)
                topPadding: 0
                bottomPadding: 0
                verticalAlignment: TextInput.AlignVCenter
                font.family: theme.bodyFamily
                font.pixelSize: theme.bodySize
                font.weight: theme.bodyWeight
                color: field.enabled ? theme.textPrimary : theme.textDisabled
                selectionColor: theme.selection
                selectedTextColor: theme.onSelection
                placeholderTextColor: field.enabled ? theme.textTertiary : theme.textDisabled
                hoverEnabled: false
                selectByMouse: true
                cursorDelegate: C.Caret {}
                background: null
                Accessible.name: field.accessibleName
                Accessible.description: field.hasError ? field.error : ""
                onAccepted: field.accepted()

                C.Txt {  // Templates draw no placeholder: this is it. 3 px in from the text's origin, so the empty field's caret (2 px) sits before it, not over its first letter
                    x: input.leftPadding + 3
                    width: input.width - input.leftPadding - input.rightPadding - 3
                    anchors.verticalCenter: parent.verticalCenter
                    visible: input.text.length === 0 && input.preeditText.length === 0
                    text: input.placeholderText
                    textStyle: "body"
                    color: input.placeholderTextColor
                    elide: Text.ElideRight
                    Accessible.ignored: true
                }
            }

            T.AbstractButton {
                id: clearBtn
                visible: field.showClear
                width: 24
                height: 24
                x: parent.width - width - (field.capsule ? 6 : 4)
                anchors.verticalCenter: parent.verticalCenter
                focusPolicy: Qt.NoFocus
                hoverEnabled: true
                Accessible.role: Accessible.Button
                Accessible.name: "Clear"
                onClicked: { field.clear(); input.forceActiveFocus() }
                HoverHandler { cursorShape: Qt.ArrowCursor }
                background: C.Fill {
                    radius: height / 2
                    hovered: clearBtn.hovered
                    pressed: clearBtn.down
                    tint: clearBtn.down ? theme.fillPressed : clearBtn.hovered ? theme.fillHover : Qt.alpha(theme.fillHover, 0)
                }
                contentItem: Item {
                    C.Icon {
                        anchors.centerIn: parent
                        name: "close"
                        size: 12
                        color: clearBtn.hovered ? theme.textPrimary : theme.textSecondary
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
            C.Icon {
                name: "warning"
                size: 12
                color: theme.dangerText
                Layout.alignment: Qt.AlignTop
                Layout.topMargin: 2
            }
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
