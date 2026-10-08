// A one-shot entrance for an item (design v4 motion): it fades in and rises theme.riseItem px
// over theme.motionReveal ms, OutCubic, after `delay`. Nothing loops; under reduced motion it
// does nothing (the page's own fade is enough). C.Page makes one per content item and plays them
// staggered when the page opens; Home does the same for its cards and first rows.
//   C.Reveal { id: reveal; target: card }   …   reveal.play(35)
import QtQuick

QtObject {
    id: reveal
    property Item target: null
    property real rise: theme.riseItem
    property Translate shift: Translate {}
    property bool attached: false

    function attach() {
        if (attached || !target) return
        const list = []
        for (let i = 0; i < target.transform.length; i++) list.push(target.transform[i])
        list.push(shift)
        target.transform = list
        attached = true
    }
    function play(delay) {
        if (!target || backend.reducedMotion) return
        attach()
        anim.stop()
        pause.duration = Math.max(0, delay || 0)
        target.opacity = 0
        shift.y = rise
        anim.start()
    }
    function finish() {
        anim.stop()
        if (target) target.opacity = 1
        shift.y = 0
    }

    property SequentialAnimation anim: SequentialAnimation {
        PauseAnimation { id: pause; duration: 0 }
        ParallelAnimation {
            NumberAnimation { target: reveal.target; property: "opacity"; to: 1; duration: theme.motionReveal; easing.type: Easing.OutCubic }
            NumberAnimation { target: reveal.shift; property: "y"; to: 0; duration: theme.motionReveal; easing.type: Easing.OutCubic }
        }
    }
}
