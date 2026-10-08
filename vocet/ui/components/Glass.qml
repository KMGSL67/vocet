// A glass surface of one kind, coloured from theme (design v4 "Calm glass"). Fills its
// parent (put it first, so content draws on top). Static, one GPU pass (C.GlassShape).
//   C.Glass { anchors.fill: parent; kind: "card"; radius: theme.radiusCard }
// kind:
//   pane      the floating sidebar: functional glass, rim lit from above, a soft shadow
//   card      content (groups, Home's cards): quieter than a pane, a softer rim and shadow
//   control   secondary buttons, pop-ups, keycaps: a raised glass capsule
//   thumb     the selected segment: a brighter lens with a small shadow
//   track     a segmented control's or switch's groove: flat, no shadow
//   field     a text field's well: flat, an even rim
//   navSel    the sidebar's selection: a neutral lens (the accent stays for the icon)
//   accent    the primary button: the accent's own gradient, a faint sheen, no glow
//   elevated  menus, the toast, dialogs: opaque bgElevated (level 2: a deeper shadow)
// sliceTop / sliceBottom: see GlassShape (a history row drawing its part of the day's card).
import QtQuick
import "." as C

Item {
    id: glass
    property string kind: "card"
    property real radius: theme.radiusCard
    property int level: 1               // elevated only
    property bool shadow: true
    property bool sliceTop: false
    property bool sliceBottom: false
    property real rimSpanTop: -1
    property real rimSpanBottom: -1
    readonly property bool dark: theme.mode === "dark"
    readonly property bool mono: theme.accentName === "mono"
    readonly property color clear: Qt.rgba(0, 0, 0, 0)

    readonly property var look: {
        const t = theme
        switch (kind) {
        case "pane": return { top: t.glassTop, bottom: t.glassBottom, sheen: t.sheen, spec: t.spec, specR: 300,
                              rimTop: t.rimTop, rimMid: t.rimMid, rimBottom: t.rimBottom, diag: 0.8,
                              shadow: t.glassShadow, blur: t.sideShadowBlur, dy: t.sideShadowY }
        case "control": return { top: t.controlTop, bottom: t.controlBottom, sheen: t.sheen, spec: t.spec,
                                 specR: width * 0.5, rimTop: t.rimTop, rimMid: t.rimMid, rimBottom: t.rimBottom,
                                 diag: 0.8, shadow: t.shadowSoft, blur: t.ctrlShadowBlur, dy: t.ctrlShadowY }
        case "keycap": return { top: t.controlTop, bottom: t.controlBottom, sheen: clear, spec: t.spec,
                                specR: width, rimTop: t.rimTop, rimMid: t.rimMid, rimBottom: t.rimBottom,
                                diag: 0.8, shadow: t.shadowSoft, blur: 4, dy: 1 }
        case "thumb": return { top: t.segThumbTop, bottom: t.segThumbBottom, sheen: t.sheen, spec: t.spec,
                               specR: width * 0.5, rimTop: t.rimTop, rimMid: t.rimMid, rimBottom: t.rimBottom,
                               diag: 0.8, shadow: t.shadowSoft, blur: t.ctrlShadowBlur, dy: t.ctrlShadowY }
        case "track": return { top: t.track, bottom: t.track, sheen: clear, spec: clear, specR: 1,
                               rimTop: t.rimTop, rimMid: t.rimMid, rimBottom: t.rimBottom, diag: 0.3,
                               shadow: clear, blur: 0, dy: 0 }
        case "field": return { top: t.fieldFill, bottom: t.fieldFill, sheen: clear, spec: clear, specR: 1,
                               rimTop: t.fieldRim, rimMid: t.fieldRim, rimBottom: t.fieldRim, diag: 0,
                               shadow: clear, blur: 0, dy: 0 }
        case "navSel": return { top: t.navSelTop, bottom: t.navSelBottom, sheen: clear, spec: clear, specR: 1,
                                rimTop: t.navSelRim, rimMid: t.navSelRim, rimBottom: t.navSelRim, diag: 0,
                                shadow: clear, blur: 0, dy: 0 }
        case "accent": return { top: t.accentTop, bottom: t.accentBottom,
                                sheen: Qt.rgba(1, 1, 1, mono ? 0 : t.btnSheen), spec: clear, specR: 1,
                                rimTop: t.btnRimTop, rimMid: Qt.alpha(t.btnRimTop, 0.25),
                                rimBottom: mono ? clear : t.btnRimBottom, diag: 0, shadow: clear, blur: 0, dy: 0 }
        case "elevated": return { top: t.bgElevated, bottom: t.bgElevated, sheen: dark ? t.sheen : clear, spec: clear,
                                  specR: 1, rimTop: dark ? t.rimTop : t.cardRimTop, rimMid: dark ? t.rimMid : t.cardRimTop,
                                  rimBottom: dark ? t.rimBottom : t.cardRimBottom, diag: 0,
                                  shadow: level === 2 ? t.shadow2 : t.shadow1, blur: level === 2 ? 36 : 16,
                                  dy: level === 2 ? 12 : 4 }
        default: return { top: t.cardTop, bottom: t.cardBottom, sheen: clear, spec: clear, specR: 1,   // card
                          rimTop: t.cardRimTop, rimMid: t.cardRimMid, rimBottom: t.cardRimBottom,
                          diag: t.cardRimDiag, shadow: t.shadowSoft, blur: t.cardShadowBlur, dy: t.cardShadowY }
        }
    }

    Accessible.ignored: true

    C.GlassShape {
        radius: glass.radius
        cFillTop: glass.look.top
        cFillBottom: glass.look.bottom
        cSheen: glass.look.sheen
        sheenH: Math.min(56, glass.height * 0.5)
        cSpec: glass.look.spec
        specR: glass.look.specR
        cRimTop: glass.look.rimTop
        cRimMid: glass.look.rimMid
        cRimBottom: glass.look.rimBottom
        rimDiag: glass.look.diag
        cShadow: glass.shadow ? glass.look.shadow : glass.clear
        shadowBlur: glass.shadow ? glass.look.blur : 0
        shadowY: glass.shadow ? glass.look.dy : 0
        sliceTop: glass.sliceTop
        sliceBottom: glass.sliceBottom
        rimSpanTop: glass.rimSpanTop
        rimSpanBottom: glass.rimSpanBottom
    }
}
