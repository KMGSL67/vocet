// The search field: a TextField with a leading search glyph (16 px, textTertiary),
// a fixed 240 px at the trailing end of the page header. Filters as you type: searched(query)
// fires 120 ms after the last keystroke (at once when cleared). Esc clears; a second Esc emits
// escapedEmpty() so the page can return focus to the list; ↓ emits downPressed() to move into
// the results. Ctrl+F (Main) calls the page's focusSearch(), which calls focusAndSelect().
//   headerAction: C.SearchField { id: search; onSearched: (q) => backend.search(q) }
import QtQuick
import "." as C

C.TextField {
    id: search
    property int debounce: 120
    signal searched(string query)
    signal escapedEmpty()
    signal downPressed()

    function focusAndSelect() {
        input.forceActiveFocus(Qt.ShortcutFocusReason)
        input.selectAll()
    }

    implicitWidth: 240
    iconName: "search"
    capsule: true
    placeholderText: "Search history"
    accessibleName: "Search history"

    onTextChanged: timer.restart()
    onCleared: { timer.stop(); searched("") }
    Keys.onEscapePressed: (event) => {
        if (text.length > 0) { clear(); event.accepted = true }
        else escapedEmpty()
    }
    Keys.onDownPressed: downPressed()
    Timer { id: timer; interval: search.debounce; onTriggered: search.searched(search.text) }
}
