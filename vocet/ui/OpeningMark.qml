// The opening mark: "vocet" types itself at a blinking caret, the letters fold in
// pairs (vo, ce, t) into the three sound bars, the bars slide into the caret, and that is the
// logo. It then shrinks onto the sidebar lockup, with identical geometry, so nothing jumps.
// Main.qml loads it in a Loader once per session (greet()) and unloads it on done().
//
// One clock: a single linear NumberAnimation drives `t` (ms) from 0 to `total`; every beat is a
// pure function of t with explicit start and duration. No FrameAnimation, no loops, no sound.
// Scripts can set `manual` and step `t` to render single frames.
// Skip: any mouse press or wheel (consumed), any key (passed on) or the window going inactive
// jumps to the end with a 120 ms crossfade. Reduced motion: only a 150 ms fade of the content.
// While it plays, the sidebar's own lockup is hidden (Sidebar.glyphOpacity / wordOpacity): the
// mark lands exactly on the glyph, and the wordmark fades in as it arrives.
//
//   OpeningMark { nav: sidebar; stage: content; onDone: loader.active = false }
import QtQuick

FocusScope {
    id: mark
    objectName: "openingMark"
    required property Item nav         // C.Sidebar: the mark lands on its logoSlot
    required property Item stage       // the content area; the word types itself in its centre
    readonly property Item slot: nav.logoSlot
    readonly property bool wordmark: !nav.rail
    readonly property bool reduced: backend.reducedMotion
    property bool manual: false        // true: the clock is stopped and t is set from outside
    property real t: 0
    readonly property real total: reduced ? theme.motionBase : tEnd
    signal done()

    // ---------------------------------------------------------------- the timeline (ms)
    // About 2.4 s, not too fast: the word types at a readable pace, the caret
    // blinks once, the letters fold into the three bars, the bars close on the caret, and the
    // logo lands on the sidebar. Every beat is a pure function of t.
    readonly property int tCaretIn: 160                 // 0-160: the caret fades in
    readonly property int tType: 260                    // the first letter
    readonly property int typeStep: 100                 // then one every 100 ms (five letters: 260-760)
    readonly property int letterIn: 70                  // each letter fades in over 70 ms
    readonly property int tBlinkOff: 900                // the hold: one caret blink, no fade
    readonly property int tBlinkOn: 1100
    readonly property int tFold: 1220                   // pairs fold, 60 ms apart
    readonly property int foldStagger: 60
    readonly property int letterOut: 260                // the squeeze
    readonly property int letterFade: 170
    readonly property int barGrow: 300
    readonly property int tClose: 1480                  // the bars slide to the caret, tallest first
    readonly property int closeStagger: 40
    readonly property int closeDur: 300
    readonly property int serifDur: 140                 // the I-beam serifs, in the last 140 ms
    readonly property int tLogo: tClose + 2 * closeStagger + closeDur          // 1860: the logo
    readonly property int tHandoff: tLogo + 60                                  // a beat, then it moves
    readonly property int handoffDur: 360                                       // 1920-2280
    readonly property int tReveal: tHandoff + 60       // the page appears under it, once the mark moves off
    readonly property int revealDur: tEnd - tReveal
    readonly property int tWord: tHandoff + handoffDur                          // the wordmark, once the glyph has landed
    readonly property int wordDur: 120
    readonly property int tEnd: tWord + wordDur                                 // 2400
    signal revealing()                                  // at tReveal: Main lets the page's content arrive
    property bool revealed: false
    onTChanged: if (!revealed && t >= tReveal) { revealed = true; revealing() }

    // ---------------------------------------------------------------- easing
    function seg(start, dur) { return Math.max(0, Math.min(1, (t - start) / dur)) }
    function outCubic(p) { return 1 - Math.pow(1 - p, 3) }
    function inOutCubic(p) { return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2 }
    function mix(a, b, p) { return a + (b - a) * p }
    function bezier(p1x, p1y, p2x, p2y, p) {  // CSS-style cubic-bezier(p1x, p1y, p2x, p2y)
        if (p <= 0 || p >= 1) return p
        const bx = (u) => 3 * p1x * u * (1 - u) * (1 - u) + 3 * p2x * u * u * (1 - u) + u * u * u
        let lo = 0, hi = 1, u = p
        for (let i = 0; i < 24; i++) {  // bisection: monotonic in u, converges to < 1e-7
            u = (lo + hi) / 2
            if (bx(u) < p) lo = u; else hi = u
        }
        return 3 * p1y * u * (1 - u) * (1 - u) + 3 * p2y * u * u * (1 - u) + u * u * u
    }
    readonly property var ez: theme.easeEmphasized
    function emphasized(p) { return bezier(ez[0], ez[1], ez[2], ez[3], p) }

    // ---------------------------------------------------------------- geometry
    // Hero: 44 px type, a 52 px glyph (bars 18 / 28 / 40). Logo.qml's formula, for any height h:
    // bar width h * 22/18 / 6.45, bars 1.85 bars apart, the caret centred 6 bars in.
    readonly property real heroH: 52
    readonly property var rest: [0.34, 0.54, 0.76]
    readonly property var alphas: [theme.logoBarA1, theme.logoBarA2, theme.logoBarA3]  // as Logo.qml
    function barW(h) { return h * 22 / 18 / 6.45 }
    readonly property real typeCaret: 2.5               // the typing caret's stroke

    readonly property string word: "vocet"
    FontMetrics { id: fm; font: hero.font }
    Text { id: hero; visible: false; font.family: "Segoe UI Variable Display Semibold"; font.pixelSize: 44
           font.weight: Font.DemiBold; font.letterSpacing: -0.4; text: mark.word; renderType: Text.CurveRendering }
    // advance to the left edge of letter i (kerning kept: measured on the prefix)
    function adv(i) { return i <= 0 ? 0 : fm.advanceWidth(word.substring(0, i)) }
    readonly property real wordW: adv(word.length) - hero.font.letterSpacing
    readonly property real caretGap: 1.5                // caret centre past the last advance

    readonly property point stageC: Qt.point(stage.x + stage.width / 2, stage.y + stage.height * 0.46)
    readonly property real wordLeft: Math.round(stageC.x - (wordW + caretGap) / 2)
    readonly property real textBase: Math.round(stageC.y + (fm.ascent - fm.descent) / 2 - 1)
    readonly property real caretEndX: wordLeft + wordW + caretGap                // caret centre, typed
    readonly property real heroLeft: caretEndX - 6 * barW(heroH)                // glyph box, hero
    readonly property real heroTop: stageC.y - heroH / 2
    function pairCentre(k) { return wordLeft + (adv(2 * k) + adv(2 * k + 2)) / 2 }

    // the landing: the sidebar's lockup, in this item's coordinates
    readonly property point slotPos: {
        if (!slot) return Qt.point(20, 14)
        slot.x; slot.y; mark.width  // dependencies: mapToItem alone doesn't re-evaluate
        return slot.mapToItem(mark, 0, 0)
    }
    readonly property real slotH: slot ? slot.height : 18

    // ---------------------------------------------------------------- derived state
    readonly property real handoffP: inOutCubic(seg(tHandoff, handoffDur))  // done at tWord: the glyph rests
    readonly property real glyphH: mix(heroH, slotH, handoffP)
    readonly property real glyphX: mix(heroLeft, slotPos.x, handoffP)
    readonly property real glyphY: mix(heroTop, slotPos.y, handoffP)
    readonly property real bw: barW(glyphH)
    readonly property real closeAll: emphasized(seg(tClose, closeDur + 2 * closeStagger))
    readonly property real serifP: outCubic(seg(tLogo - serifDur, serifDur))
    readonly property real caretTyped: {  // the caret's x offset while typing, in 40 ms steps
        let x = 0
        for (let k = 0; k < word.length; k++)
            x += (adv(k + 1) - adv(k)) * outCubic(seg(tType + k * typeStep, letterIn))
        return x
    }
    readonly property real caretCx: t < tHandoff ? wordLeft + caretTyped + caretGap * seg(tType, letterIn)
                                                 : glyphX + 6 * bw

    // ---------------------------------------------------------------- clock and skip
    NumberAnimation {
        id: clock
        target: mark
        property: "t"
        from: 0
        to: mark.total
        duration: mark.total
        onFinished: mark.finish()
    }
    NumberAnimation {  // skip: the overlay fades out over the end state underneath
        id: skipFade
        target: mark
        property: "opacity"
        to: 0
        duration: 120
        easing.type: Easing.OutCubic
        onFinished: mark.finish()
    }
    property bool ended: false
    function finish() {
        if (ended) return
        ended = true
        clock.stop()
        if (restoreFocus && restoreFocus.forceActiveFocus) restoreFocus.forceActiveFocus()
        done()
    }
    function skip() {
        if (ended || skipFade.running || manual) return
        clock.stop()
        skipFade.start()  // the real end state is underneath
    }
    onManualChanged: if (manual) { clock.stop(); skipFade.stop(); opacity = 1 }

    property Item restoreFocus: null
    Component.onCompleted: {
        restoreFocus = Window.activeFocusItem
        forceActiveFocus()
        clock.start()
    }

    Keys.onPressed: (event) => { mark.skip(); event.accepted = false }  // shortcuts still work
    Connections {
        target: mark.Window.window
        function onActiveChanged() { if (!mark.Window.window.active) mark.skip() }
    }
    MouseArea {  // the press that skips is consumed, so it can't hit a control not yet visible
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onPressed: mark.skip()
        onWheel: (wheel) => { mark.skip(); wheel.accepted = true }
    }

    // ---------------------------------------------------------------- the picture
    // The sidebar's lockup hides while the mark plays: the glyph until the mark has landed on it
    // (same geometry, so nothing jumps), the wordmark fading in as the glyph arrives. The Bindings
    // restore both when the mark unloads.
    Binding { target: mark.nav; property: "glyphOpacity"; value: mark.reduced || mark.ended || mark.skipping ? 1 : 0 }
    Binding {
        target: mark.nav
        property: "wordOpacity"
        value: mark.reduced || mark.ended || mark.skipping ? 1 : mark.outCubic(mark.seg(mark.tWord, mark.wordDur))
    }
    readonly property bool skipping: skipFade.running

    Rectangle {  // covers the window until the page appears under the mark
        anchors.fill: parent
        color: theme.bgWindow
        opacity: mark.reduced ? 1 - mark.seg(0, mark.total) : 1 - mark.inOutCubic(mark.seg(mark.tReveal, mark.revealDur))
    }

    Item {
        id: art
        anchors.fill: parent
        visible: !mark.reduced

        Repeater {  // the typed letters; folding, each pair closes like a fan into its bar
            model: mark.word.length
            Text {
                id: letter
                required property int index
                readonly property int pair: Math.floor(index / 2)
                readonly property real foldP: mark.inOutCubic(mark.seg(mark.tFold + pair * mark.foldStagger, mark.letterOut))
                x: mark.wordLeft + mark.adv(index)
                y: mark.textBase - fm.ascent
                text: mark.word.charAt(index)
                font: hero.font
                renderType: Text.CurveRendering  // its own glyph cache: sharing the distance-field one would re-render the page's type when this unloads
                color: theme.textPrimary
                transform: Scale {
                    origin.x: mark.mix(letter.width / 2, mark.pairCentre(letter.pair) - letter.x, 0.4)  // each thins, and leans in
                    origin.y: fm.ascent - fm.xHeight / 2
                    xScale: 1 - 0.9 * letter.foldP
                    yScale: 1 - 0.15 * letter.foldP
                }
                // gone before the squeeze ends, so a folding "nn" never reads as an "m"
                opacity: mark.seg(mark.tType + index * mark.typeStep, mark.letterIn)
                         * (1 - mark.inOutCubic(mark.seg(mark.tFold + pair * mark.foldStagger, mark.letterFade)))
                visible: opacity > 0
            }
        }

        Repeater {  // the bars: each rises out of its folding pair, then slides in to the caret
            model: 3
            Rectangle {
                required property int index
                readonly property int start: mark.tFold + index * mark.foldStagger
                readonly property real growP: mark.inOutCubic(mark.seg(start + 20, mark.barGrow))
                readonly property real closeP: mark.emphasized(mark.seg(mark.tClose + (2 - index) * mark.closeStagger, mark.closeDur))
                readonly property real fromX: mark.pairCentre(index) - width / 2
                readonly property real toX: mark.glyphX + index * mark.bw * 1.85
                // from the letters' x-height, centred on it, to the logo's bar, centred on the caret
                readonly property real fromCy: mark.textBase - fm.xHeight / 2
                readonly property real toCy: mark.glyphY + mark.glyphH / 2
                width: mark.bw
                radius: width / 2
                height: mark.mix(fm.xHeight * 0.9, mark.glyphH * mark.rest[index], growP)
                x: mark.mix(fromX, toX, closeP)
                y: mark.mix(fromCy, toCy, growP) - height / 2
                color: theme.accent  // the same ink as Logo.qml, so the landing has no colour jump
                opacity: mark.alphas[index] * mark.outCubic(mark.seg(start + 25, 60))
                visible: opacity > 0
            }
        }

        Item {  // the caret: a text caret while typing, the logo's I-beam at the end
            readonly property real stroke: mark.mix(mark.typeCaret, mark.bw * 0.52, mark.closeAll)
            readonly property real serif: mark.mix(stroke, stroke * 3.2, mark.serifP)
            x: mark.caretCx - serif / 2
            y: mark.glyphY
            width: serif
            height: mark.glyphH
            opacity: mark.outCubic(mark.seg(0, mark.tCaretIn)) * (mark.t >= mark.tBlinkOff && mark.t < mark.tBlinkOn ? 0 : 1)
            Rectangle { x: (parent.width - width) / 2; width: parent.stroke; height: parent.height; radius: width / 2; color: theme.textPrimary }
            Rectangle { x: (parent.width - width) / 2; width: parent.serif; height: parent.stroke; radius: height / 2; color: theme.textPrimary }
            Rectangle { x: (parent.width - width) / 2; width: parent.serif; height: parent.stroke; radius: height / 2; y: parent.height - height; color: theme.textPrimary }
        }
    }
}
