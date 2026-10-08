// An indeterminate spinner: 16 px, 2 px stroke, textSecondary, one turn per second.
// Only while an operation runs: it turns while `running` is true AND its window is on screen
// (hidden or minimised = nothing runs), one turn at a time, so it can never idle-loop.
//   C.Spinner { running: backend.status.startsWith("Loading") }
import QtQuick
import QtQuick.Shapes

Item {
    id: spinner
    property bool running: true
    property int size: 16
    property color color: theme.textSecondary
    readonly property bool live: running && visible && Window.window !== null
                                 && Window.visibility !== Window.Hidden && Window.visibility !== Window.Minimized
    implicitWidth: size
    implicitHeight: size
    Accessible.role: Accessible.Animation
    Accessible.name: "Working"

    onLiveChanged: live ? turn.start() : turn.stop()
    Component.onCompleted: if (live) turn.start()

    Shape {
        id: arc
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: spinner.color
            strokeWidth: 2
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: spinner.size / 2
                centerY: spinner.size / 2
                radiusX: spinner.size / 2 - 1
                radiusY: spinner.size / 2 - 1
                startAngle: -90
                sweepAngle: 270
            }
        }
    }
    RotationAnimator {
        id: turn
        target: arc
        from: 0
        to: 360
        duration: 1000
        onFinished: if (spinner.live) start()   // the next turn, only while still needed
    }
}
