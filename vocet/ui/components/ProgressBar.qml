// A determinate progress bar: 4 px, radius 2, fillControl track, accent fill.
// Its label (yours) says what's happening: "Loading speech model… 42 %", never just "Loading".
//   C.ProgressBar { value: 0.42; label: "Loading speech model" }
import QtQuick
import QtQuick.Templates as T

T.ProgressBar {
    id: bar
    property string label: ""
    from: 0
    to: 1
    implicitWidth: 200
    implicitHeight: 4
    Accessible.name: label

    background: Rectangle {
        radius: 2
        color: theme.fillControl
        border.width: theme.highContrast ? 1 : 0
        border.color: theme.strokeStrong
    }
    contentItem: Item {
        Rectangle {
            width: Math.max(bar.visualPosition > 0 ? 4 : 0, bar.visualPosition * parent.width)
            height: parent.height
            radius: 2
            color: theme.accent
            Behavior on width { enabled: !backend.reducedMotion; NumberAnimation { duration: theme.motionMedium; easing.type: Easing.OutCubic } }
        }
    }
}
