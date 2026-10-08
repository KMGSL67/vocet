// The app a dictation went into (design v4): a monochrome glyph for the kind of app (mail,
// notes, chat, code, browser, document, terminal, or a generic app) in a neutral circle. Calm by
// design: the program's own colourful icon stays out of the list. `realIcon: true` shows
// the program's icon instead (served by window.py's AppIconProvider), for places that need it.
//   C.AppIcon { app: model.app; path: model.appPath }        // a 32 px circle
import QtQuick
import "." as C

Item {
    id: appIcon
    property string app: ""
    property string path: ""
    property int size: 32
    property bool realIcon: false
    readonly property string key: (app + " " + path.split(/[\\/]/).pop()).toLowerCase()
    readonly property string kind: {
        const k = key
        const has = (words) => words.some(w => k.indexOf(w) >= 0)
        if (has(["outlook", "mail", "thunderbird", "hxoutlook"])) return "mail"
        if (has(["teams", "slack", "discord", "whatsapp", "telegram", "signal", "zoom"])) return "chats"
        if (has(["messages", "messenger", "chat"])) return "chat"
        if (has(["code", "visual studio", "devenv", "pycharm", "idea", "sublime", "cursor", "notepad++"])) return "code"
        if (has(["chrome", "edge", "msedge", "firefox", "brave", "opera", "vivaldi", "safari", "browser"])) return "globe"
        if (has(["notepad", "notes", "onenote", "obsidian", "notion", "sticky"])) return "note"
        if (has(["word", "winword", "docs", "writer", "pages", "acrobat", "powerpnt", "excel"])) return "document"
        if (has(["terminal", "powershell", "cmd", "windowsterminal", "wt.exe"])) return "terminal"
        return "app"
    }
    implicitWidth: size
    implicitHeight: size
    Accessible.ignored: true

    Rectangle {
        visible: !appIcon.realIcon
        anchors.fill: parent
        radius: width / 2
        color: theme.tileFill
        border.width: theme.highContrast ? 1 : 0
        border.color: theme.strokeStrong
        antialiasing: true
    }
    C.Icon {
        visible: !appIcon.realIcon || !img.visible
        anchors.centerIn: parent
        name: appIcon.kind
        size: appIcon.realIcon ? appIcon.size : Math.round(appIcon.size * 0.47)
        color: theme.textSecondary
    }
    Image {
        id: img
        anchors.fill: parent
        source: appIcon.realIcon && appIcon.path ? "image://appicon/" + encodeURIComponent(appIcon.path) : ""
        sourceSize: Qt.size(64, 64)
        smooth: true
        mipmap: true
        visible: appIcon.realIcon && status === Image.Ready && implicitWidth > 1   // 1 px: the provider has no real icon
    }
}
