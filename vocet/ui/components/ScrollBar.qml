// The overlay scroll bar. While scrolling: a 4 px strokeStrong thumb, radius 2,
// inset 3 px, no track, at least 32 px long. Hovered: 8 px, textSecondary, on a fillHover
// track. Hides 800 ms after scrolling stops (300 ms fade) unless Windows' "Always show
// scrollbars" is on (backend.alwaysShowScrollbars, when the backend provides it).
// C.Page attaches one for you. For your own ListView:
//   import QtQuick.Templates as T
//   ListView { T.ScrollBar.vertical: C.ScrollBar {} ; boundsBehavior: Flickable.StopAtBounds }
import QtQuick
import QtQuick.Templates as T

T.ScrollBar {
    id: bar
    readonly property bool alwaysShow: backend.alwaysShowScrollbars === true
    readonly property bool wide: hovered || pressed
    readonly property bool isVertical: orientation === Qt.Vertical

    hoverEnabled: true
    minimumSize: 32 / Math.max(32, isVertical ? height : width)
    policy: T.ScrollBar.AsNeeded
    visible: size < 1.0
    implicitWidth: 14
    implicitHeight: 14
    topPadding: 3
    bottomPadding: 3
    rightPadding: 3
    leftPadding: 3
    opacity: 0

    contentItem: Item {
        implicitWidth: 8
        implicitHeight: 8
        Rectangle {
            readonly property real thickness: bar.wide ? 8 : 4
            width: bar.isVertical ? thickness : parent.width
            height: bar.isVertical ? parent.height : thickness
            anchors.right: bar.isVertical ? parent.right : undefined
            anchors.bottom: bar.isVertical ? undefined : parent.bottom
            radius: thickness / 2
            color: bar.wide ? theme.textSecondary : theme.strokeStrong
            Behavior on width { enabled: !backend.reducedMotion; NumberAnimation { duration: theme.motionFast } }
            Behavior on height { enabled: !backend.reducedMotion; NumberAnimation { duration: theme.motionFast } }
        }
    }
    background: Rectangle {
        color: theme.fillHover
        opacity: bar.wide ? 1 : 0
        radius: 6
    }

    states: State {
        name: "shown"
        when: bar.active || bar.hovered || bar.pressed || bar.alwaysShow
        PropertyChanges { bar.opacity: 1 }
    }
    transitions: [
        Transition {
            to: "shown"
            NumberAnimation { property: "opacity"; duration: theme.motionFast }
        },
        Transition {
            from: "shown"
            SequentialAnimation {
                PauseAnimation { duration: 800 }
                NumberAnimation { property: "opacity"; duration: backend.reducedMotion ? theme.motionFast : 300 }
            }
        }
    ]
}
