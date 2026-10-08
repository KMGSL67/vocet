// The Vocet window (design v4 "Calm glass"): a pure black (or white) window, a floating
// glass sidebar and the page. Closing it only hides it: Vocet keeps running in the tray.
//
// Pages: "home" (HistoryPage.qml; "history" is accepted too), "dictionary", "snippets", "settings".
// window.py/app.py pick one with show("settings"), which sets `page`.
// A new page fades in and rises 8 px (240 ms OutCubic) while the old one hides at once, and its
// content items reveal 35 ms apart (C.Page.revealContent). Reduced motion: a 100 ms fade only.
// Page contract: a page is an Item filling its slot, with `property bool active` (true while
// it's the current page). Home may offer focusSearch() for Ctrl+F.
import QtQuick
import QtQuick.Controls.Basic
import "components" as C

ApplicationWindow {
    id: root
    width: 1080
    height: 720
    minimumWidth: 640
    minimumHeight: 480
    visible: false
    title: "Vocet"
    color: theme.bgWindow
    font.family: theme.bodyFamily
    font.pixelSize: theme.bodySize

    property string page: "home"
    property bool allowClose: false          // set by Python only when Vocet quits
    readonly property var pageNames: ["home", "dictionary", "snippets", "settings"]
    readonly property string current: page === "history" ? "home" : pageNames.indexOf(page) >= 0 ? page : "home"
    readonly property bool rail: width < 760

    function navigate(name) { root.page = name }
    property bool greeted: false
    function greet() {                       // window.py calls this on every show: the mark plays once per session,
        if (greeted) return                  // and never while you're dictating
        greeted = true
        if (!backend.listening) opening.active = true
    }

    onClosing: (close) => {
        if (backend.welcomeOpen)             // closing the window counts as skipping the welcome
            backend.finishWelcome(true, welcomeLoader.item ? welcomeLoader.item.step : 0)
        if (!root.allowClose) { close.accepted = false; root.hide() }
    }

    // While the welcome is up, the page shortcuts wait: it's the only thing on screen.
    readonly property bool pagesEnabled: !backend.welcomeOpen
    Shortcut { sequence: "Ctrl+1"; enabled: root.pagesEnabled; onActivated: root.navigate("home") }
    Shortcut { sequence: "Ctrl+2"; enabled: root.pagesEnabled; onActivated: root.navigate("dictionary") }
    Shortcut { sequence: "Ctrl+3"; enabled: root.pagesEnabled; onActivated: root.navigate("snippets") }
    Shortcut { sequence: "Ctrl+4"; enabled: root.pagesEnabled; onActivated: root.navigate("settings") }
    Shortcut { sequence: "Ctrl+,"; enabled: root.pagesEnabled; onActivated: root.navigate("settings") }
    Shortcut {
        enabled: root.pagesEnabled
        sequence: "Ctrl+F"
        onActivated: {
            root.navigate("home")
            if (typeof home.focusSearch === "function") home.focusSearch()
        }
    }
    Shortcut {  // undo a delete, with or without the toast (text fields keep their own Ctrl+Z)
        enabled: root.pagesEnabled
        sequence: "Ctrl+Z"
        onActivated: { backend.undoDelete(); toast.hide() }
    }

    Connections {
        target: backend
        function onToast(message, undoable) {
            toast.show(message, undoable ? { action: "Undo", onAction: () => backend.undoDelete() } : {})
        }
    }

    component PageSlot: FocusScope {
        id: slot
        required property string name
        property string current: ""
        readonly property bool shown: current === name
        readonly property Item page: children.length > 0 ? children[0] : null
        anchors.fill: parent
        visible: shown
        focus: shown
        onShownChanged: if (shown) enter()
        function enter() {
            fade.stop()
            opacity = 0
            rise.y = backend.reducedMotion ? 0 : theme.risePage
            fade.start()
            if (page && typeof page.revealContent === "function") page.revealContent()
        }
        transform: Translate { id: rise }
        ParallelAnimation {
            id: fade
            NumberAnimation {
                target: slot
                property: "opacity"
                to: 1
                duration: backend.reducedMotion ? theme.motionFast : theme.motionPage
                easing.type: Easing.OutCubic
            }
            NumberAnimation {
                target: rise
                property: "y"
                to: 0
                duration: backend.reducedMotion ? 0 : theme.motionPage + 60
                easing.type: Easing.OutCubic
            }
        }
    }

    function revealCurrent() {  // after the opening mark: the page's content arrives
        const slots = [homeSlot, dictionarySlot, snippetsSlot, settingsSlot]
        for (let i = 0; i < slots.length; i++)
            if (slots[i].shown && slots[i].page && typeof slots[i].page.revealContent === "function")
                slots[i].page.revealContent()
    }

    // ---------------------------------------------------------------- where the focus goes
    // When something over the page ends (the opening mark, the welcome) the keyboard focus must
    // land somewhere real, not on an unloaded Loader or the window's root. Without a control to
    // go back to it goes to the current page, so PgUp/PgDn work and Tab starts at the sidebar.
    // ring: the user was on the keyboard, so the sidebar's current item takes it, with its ring.
    function focusPage(ring) {
        if (ring) { sidebar.focusItem(sidebar.currentIndex); return }
        const slots = [homeSlot, dictionarySlot, snippetsSlot, settingsSlot]
        for (let i = 0; i < slots.length; i++)
            if (slots[i].shown) { (slots[i].page || slots[i]).forceActiveFocus(Qt.OtherFocusReason); return }
    }
    function focusIsLost() {  // on nothing, the window's root, a Loader, or a page's slot (not the page)
        const f = root.activeFocusItem
        if (!f || [content, homeSlot, dictionarySlot, snippetsSlot, settingsSlot].indexOf(f) >= 0) return true
        for (let p = f; p; p = p.parent)
            if (p === sidebar || p === content || p === root.overlay || (welcomeLoader.item && p === welcomeLoader.item)) return false
        return true
    }
    function afterOpening() {  // the mark gives the focus back (OpeningMark.restoreFocus), if it had one to give
        if (!focusIsLost()) return
        if (welcomeLoader.item) welcomeLoader.item.forceActiveFocus()
        else focusPage(false)
    }
    property Item welcomeOpener: null        // what had the focus when the welcome opened (Settings' Show again)
    property bool welcomeRing: false         // …and whether it showed its focus ring, or the welcome was left by keyboard
    function afterWelcome() {
        const back = welcomeOpener
        welcomeOpener = null
        if (back && back.visible && back.enabled) back.forceActiveFocus(welcomeRing ? Qt.TabFocusReason : Qt.OtherFocusReason)
        else if (focusIsLost()) focusPage(welcomeRing)
    }

    C.Sidebar {
        id: sidebar
        z: 2                                 // its soft shadow falls over the page's pinned header
        width: root.rail ? 76 : 248
        height: parent.height
        current: root.current
        rail: root.rail
        onNavigate: (name) => root.navigate(name)
        onResumeRequested: if (typeof backend.resume === "function") backend.resume()
        Behavior on width { enabled: !backend.reducedMotion; NumberAnimation { duration: theme.motionMedium; easing.type: Easing.InOutCubic } }
    }

    Item {
        id: content
        x: sidebar.width
        width: parent.width - sidebar.width
        height: parent.height

        PageSlot { id: homeSlot; name: "home"; current: root.current; HistoryPage { id: home; objectName: "homePage"; anchors.fill: parent; active: parent.shown } }
        PageSlot { id: dictionarySlot; name: "dictionary"; current: root.current; DictionaryPage { objectName: "dictionaryPage"; anchors.fill: parent; active: parent.shown } }
        PageSlot { id: snippetsSlot; name: "snippets"; current: root.current; SnippetsPage { objectName: "snippetsPage"; anchors.fill: parent; active: parent.shown } }
        PageSlot { id: settingsSlot; name: "settings"; current: root.current; SettingsPage { objectName: "settingsPage"; anchors.fill: parent; active: parent.shown } }

        C.Toast {  // bottom centre of the content column: never over a page header (Toast.qml)
            id: toast
            z: 10
            x: Math.round(home.columnX + (home.columnWidth - width) / 2)
            y: parent.height - height - theme.space7
        }
    }

    Loader {  // the first-run welcome, over the page and under the opening mark: loaded before
              // the first frame (window.py shows the window after backend.set_welcome_open), and it
              // only enters once the mark is done, so nothing flashes
        id: welcomeLoader
        objectName: "welcomeLoader"
        anchors.fill: parent
        z: 50
        active: backend.welcomeOpen
        focus: active
        sourceComponent: Welcome { holding: opening.active; onFinishing: (byKeyboard) => { if (byKeyboard) root.welcomeRing = true } }
        onLoaded: {
            const f = root.activeFocusItem
            root.welcomeOpener = f && f.activeFocusOnTab ? f : null
            root.welcomeRing = !!(f && f.visualFocus)
            item.forceActiveFocus()
        }
        onActiveChanged: if (!active) Qt.callLater(root.afterWelcome)
    }

    Loader {  // the opening mark, over everything; unloaded when it ends, so it costs nothing after
        id: opening
        objectName: "opening"
        anchors.fill: parent
        z: 100
        active: false
        onActiveChanged: if (!active) Qt.callLater(root.afterOpening)
        sourceComponent: OpeningMark { nav: sidebar; stage: content; onRevealing: root.revealCurrent(); onDone: Qt.callLater(() => opening.active = false) }
    }
}
