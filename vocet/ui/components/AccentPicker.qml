// Accent colour swatches: 20 px circles with 12 px gaps, a radio group. The chosen
// one has a 2 px textPrimary ring (and its name belongs in the row's description). Arrow keys
// move and choose; each swatch is announced with its name. "Black & white" (mono) is drawn as
// a split circle, black and white in either mode, with a hairline.
//   C.SettingRow {
//       title: "Accent colour"; description: picker.currentLabel
//       C.AccentPicker { id: picker; value: backend.settings.accent; onPicked: (n) => backend.setSetting("accent", n) }
//   }
// model: backend.accents, [{ name, label, fill }] with fills for the current light/dark.
import QtQuick
import QtQuick.Templates as T
import "." as C

Row {
    id: picker
    property var model: backend.accents || []
    property string value: theme.accentName
    property string label: "Accent colour"
    signal picked(string name)
    readonly property string currentLabel: {
        for (let i = 0; i < model.length; i++)
            if (model[i].name === value) return model[i].label
        return ""
    }
    readonly property real hairline: 1 / Screen.devicePixelRatio

    function choose(i) {
        if (i < 0 || i >= model.length) return
        const s = swatches.itemAt(i)
        if (s) s.forceActiveFocus(Qt.TabFocusReason)
        if (model[i].name !== value) picked(model[i].name)
    }

    spacing: 4                        // 28 px targets, so the 20 px circles sit 12 px apart
    Accessible.role: Accessible.Grouping
    Accessible.name: label

    Repeater {
        id: swatches
        model: picker.model
        T.AbstractButton {
            id: swatch
            required property var modelData
            required property int index
            readonly property bool chosen: modelData.name === picker.value
            readonly property bool mono: modelData.name === "mono"
            width: 28
            height: 28
            hoverEnabled: true
            focusPolicy: chosen ? Qt.StrongFocus : Qt.ClickFocus
            Accessible.role: Accessible.RadioButton
            Accessible.name: modelData.label
            Accessible.checkable: true
            Accessible.checked: chosen
            onClicked: picker.choose(index)
            Keys.onLeftPressed: picker.choose(index - 1)
            Keys.onRightPressed: picker.choose(index + 1)

            background: Item {
                Rectangle {  // the chosen ring: 2 px, 2 px gap
                    anchors.fill: parent
                    radius: width / 2
                    color: "transparent"
                    border.width: 2
                    border.color: theme.textPrimary
                    visible: swatch.chosen
                }
                C.FocusRing { show: swatch.visualFocus; controlRadius: 14 }
            }
            contentItem: Item {
                Rectangle {
                    id: dot
                    width: 20
                    height: 20
                    radius: 10
                    anchors.centerIn: parent
                    color: swatch.mono ? theme.bgGroup : swatch.modelData.fill
                    Item {  // mono: the left half in textPrimary
                        visible: swatch.mono
                        width: 10
                        height: 20
                        clip: true
                        Rectangle { width: 20; height: 20; radius: 10; color: theme.textPrimary }
                    }
                    Rectangle {
                        anchors.fill: parent
                        radius: 10
                        color: "transparent"
                        border.width: picker.hairline
                        border.color: swatch.mono ? theme.strokeStrong : Qt.alpha(theme.textPrimary, 0.12)
                    }
                }
                Rectangle {  // hover: a faint wash over the swatch
                    anchors.fill: dot
                    radius: 10
                    color: theme.fillHover
                    visible: swatch.hovered && !swatch.chosen
                }
            }
            C.Tooltip { text: swatch.modelData.label; visible: swatch.hovered }
        }
    }
}
