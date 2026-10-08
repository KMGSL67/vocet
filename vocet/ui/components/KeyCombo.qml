// A shortcut as keycaps: [Ctrl] + [Win], with a callout "+" in textTertiary and
// 4 px gaps. Read as one phrase by screen readers: "Ctrl plus Windows key".
//   C.KeyCombo { keys: backend.hotkeyKeys }
import QtQuick
import "." as C

Row {
    id: combo
    property var keys: []
    readonly property var spoken: ({ "Win": "Windows key", "Ctrl": "Ctrl", "Alt": "Alt", "Shift": "Shift" })
    spacing: theme.space2
    Accessible.role: Accessible.StaticText
    Accessible.name: {
        const words = []
        for (let i = 0; i < (keys ? keys.length : 0); i++)
            words.push(spoken[keys[i]] || keys[i])
        return words.join(" plus ")
    }

    Repeater {
        model: combo.keys
        Row {
            required property var modelData
            required property int index
            spacing: theme.space2
            C.Txt {
                visible: index > 0
                text: "+"
                textStyle: "callout"
                tone: "tertiary"
                anchors.verticalCenter: parent.verticalCenter
                Accessible.ignored: true
            }
            C.Keycap { label: modelData; anchors.verticalCenter: parent.verticalCenter }
        }
    }
}
