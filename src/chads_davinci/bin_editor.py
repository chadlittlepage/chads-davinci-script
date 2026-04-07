"""Cocoa window for editing the bin/folder structure.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import json
from typing import Any

import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSButton,
    NSFont,
    NSMakeRect,
    NSObject,
    NSOutlineView,
    NSScrollView,
    NSTableColumn,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)

from chads_davinci.paths import APP_SUPPORT_DIR

# Module-level retention to prevent GC of editor controllers/windows
_RETAINED = []

# Persistent storage for user-customized bin structure
SAVED_BINS_PATH = APP_SUPPORT_DIR / "bin_structure.json"


def save_bin_structure(structure: list[tuple[str, list[str]]]) -> None:
    """Persist the bin structure to disk."""
    SAVED_BINS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAVED_BINS_PATH.write_text(
        json.dumps(structure, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_saved_bin_structure() -> list[tuple[str, list[str]]] | None:
    """Load the user's saved bin structure if it exists."""
    if not SAVED_BINS_PATH.exists():
        return None
    try:
        data = json.loads(SAVED_BINS_PATH.read_text(encoding="utf-8"))
        return [(name, sub_list) for name, sub_list in data]
    except Exception:
        return None


def reset_saved_bin_structure() -> None:
    """Delete the saved bin structure file (revert to defaults)."""
    if SAVED_BINS_PATH.exists():
        SAVED_BINS_PATH.unlink()


def build_rename_map(roots: list[Any]) -> dict[str, str]:
    """Build a map of original_path -> new_path for renamed bins."""
    rename_map = {}

    def walk(node):
        orig = node.get_original_path()
        new = node.get_path()
        if orig != new:
            rename_map[orig] = new
        for child in node.children:
            walk(child)

    for root in roots:
        walk(root)
    return rename_map


class BinNode(NSObject):
    """A node in the bin tree, as an NSObject so NSOutlineView can hold it."""

    def initWithName_(self, name):
        self = objc.super(BinNode, self).init()
        if self is not None:
            self.name = name
            self.original_name = name  # Track for rename detection
            self.children = []
            self.parent = None
        return self

    def add_child(self, name):
        child = BinNode.alloc().initWithName_(name)
        child.parent = self
        self.children.append(child)
        return child

    def get_path(self):
        """Build the full path from root to this node using current names."""
        parts = []
        node = self
        while node is not None:
            parts.insert(0, node.name)
            node = node.parent
        return "/".join(parts)

    def get_original_path(self):
        """Build the full path using original names (for rename tracking)."""
        parts = []
        node = self
        while node is not None:
            parts.insert(0, node.original_name)
            node = node.parent
        return "/".join(parts)


DEFAULT_BIN_STRUCTURE = [
    ("HW5", ["Target_795", "Generic TV"]),
    ("LWL15", ["Target_795", "GenericTV"]),
    ("HWL15", ["Generic TV/HDMIScrambled", "Target_795", "Target_300"]),
    ("SOURCE", ["Long Plata Reel", "Short Plata Reel"]),
    ("HW2", ["Target_795", "Generic TV", "Target_300"]),
]


def default_bin_tree() -> list[BinNode]:
    """Build the bin tree from saved user structure or fall back to default."""
    structure = load_saved_bin_structure()
    if structure is None:
        structure = DEFAULT_BIN_STRUCTURE

    roots = []
    for top_name, sub_paths in structure:
        top = BinNode.alloc().initWithName_(top_name)
        for sub_path in sub_paths:
            parts = sub_path.split("/")
            parent = top
            for part in parts:
                # Find existing child or create
                existing = next((c for c in parent.children if c.name == part), None)
                if existing is None:
                    parent = parent.add_child(part)
                else:
                    parent = existing
        roots.append(top)
    return roots


def tree_to_structure(roots: list[BinNode]) -> list[tuple[str, list[str]]]:
    """Convert a list of BinNode roots back to BIN_STRUCTURE format."""
    result = []
    for root in roots:
        sub_paths = []
        # Walk all leaf paths under root
        def walk(node: BinNode, path_parts: list[str]) -> None:
            if not node.children:
                # Leaf — record the path
                if path_parts:
                    sub_paths.append("/".join(path_parts))
            else:
                for child in node.children:
                    walk(child, path_parts + [child.name])

        walk(root, [])
        result.append((root.name, sub_paths))
    return result


# ---------------------------------------------------------------------------
# NSOutlineView data source / delegate
# ---------------------------------------------------------------------------


class BinTreeDataSource(NSObject):
    """Data source for NSOutlineView showing the bin tree."""

    def init(self):
        self = objc.super(BinTreeDataSource, self).init()
        if self is not None:
            self.roots = []
        return self

    # NSOutlineViewDataSource protocol
    # PyObjC infers signatures from the standard NSOutlineView method names.

    def outlineView_numberOfChildrenOfItem_(self, outline_view, item):
        if item is None:
            return len(self.roots)
        return len(item.children)

    def outlineView_child_ofItem_(self, outline_view, index, item):
        if item is None:
            return self.roots[index]
        return item.children[index]

    def outlineView_isItemExpandable_(self, outline_view, item):
        return len(item.children) > 0 if item else False

    def outlineView_objectValueForTableColumn_byItem_(self, outline_view, column, item):
        return item.name if item else ""

    def outlineView_setObjectValue_forTableColumn_byItem_(
        self, outline_view, value, column, item
    ):
        if item is not None:
            item.name = str(value)


# ---------------------------------------------------------------------------
# Bin editor window controller
# ---------------------------------------------------------------------------


class BinEditorController(NSObject):
    """Controller for the bin editor window."""

    def init(self):
        self = objc.super(BinEditorController, self).init()
        if self is not None:
            self.roots = []
            self.completion = None
            self.window = None
            self.outline_view = None
            self.data_source = None
        return self

    def addTopBinClicked_(self, sender):
        new_node = BinNode.alloc().initWithName_("New Bin")
        self.roots.append(new_node)
        self.outline_view.reloadData()
        # Select and edit the new node
        row = self.outline_view.rowForItem_(new_node)
        if row >= 0:
            self.outline_view.editColumn_row_withEvent_select_(0, row, None, True)

    def addSubBinClicked_(self, sender):
        item = self.outline_view.itemAtRow_(self.outline_view.selectedRow())
        if item is None:
            return
        new_node = item.add_child("New Sub-Bin")
        self.outline_view.reloadData()
        self.outline_view.expandItem_(item)
        row = self.outline_view.rowForItem_(new_node)
        if row >= 0:
            self.outline_view.editColumn_row_withEvent_select_(0, row, None, True)

    def deleteClicked_(self, sender):
        item = self.outline_view.itemAtRow_(self.outline_view.selectedRow())
        if item is None:
            return
        if item.parent is None:
            # Top-level bin
            if item in self.roots:
                self.roots.remove(item)
        else:
            if item in item.parent.children:
                item.parent.children.remove(item)
        self.outline_view.reloadData()

    def renameClicked_(self, sender):
        row = self.outline_view.selectedRow()
        if row >= 0:
            self.outline_view.editColumn_row_withEvent_select_(0, row, None, True)

    def cancelClicked_(self, sender):
        if self.completion:
            self.completion(None)
        if self.window:
            self.window.close()

    def revertToDefaultClicked_(self, sender):
        """Discard saved customizations and reload the default structure."""
        reset_saved_bin_structure()
        # Rebuild tree from default
        self.roots.clear()
        for top_name, sub_paths in DEFAULT_BIN_STRUCTURE:
            top = BinNode.alloc().initWithName_(top_name)
            for sub_path in sub_paths:
                parts = sub_path.split("/")
                parent = top
                for part in parts:
                    existing = next((c for c in parent.children if c.name == part), None)
                    if existing is None:
                        parent = parent.add_child(part)
                    else:
                        parent = existing
            self.roots.append(top)
        if self.data_source is not None:
            self.data_source.roots = self.roots
        self.outline_view.reloadData()
        for root in self.roots:
            self.outline_view.expandItem_(root)

    def saveClicked_(self, sender):
        # Persist the new structure as default
        from chads_davinci.bin_editor import tree_to_structure
        save_bin_structure(tree_to_structure(self.roots))
        if self.completion:
            self.completion(self.roots)
        if self.window:
            self.window.close()


def show_bin_editor(initial_roots, completion) -> None:
    """Open the bin editor window. completion(roots) called on save, or None on cancel."""
    controller = BinEditorController.alloc().init()
    controller.roots = initial_roots
    controller.completion = completion

    win_w, win_h = 480, 560
    style = (
        NSWindowStyleMaskTitled
        | NSWindowStyleMaskClosable
        | NSWindowStyleMaskResizable
        | NSWindowStyleMaskMiniaturizable
    )

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(200, 200, win_w, win_h),
        style,
        NSBackingStoreBuffered,
        False,
    )
    window.setTitle_("Edit Bin Structure")
    window.setMinSize_((480, 480))
    controller.window = window

    content = window.contentView()

    margin = 16
    btn_h = 28

    # Header
    header = NSTextField.alloc().initWithFrame_(
        NSMakeRect(margin, win_h - margin - 24, win_w - 2 * margin, 24)
    )
    header.setStringValue_("Bin / Sub-Bin Structure")
    header.setBezeled_(False)
    header.setDrawsBackground_(False)
    header.setEditable_(False)
    header.setSelectable_(False)
    header.setFont_(NSFont.boldSystemFontOfSize_(14))
    # Header sticks to TOP: width flex (2) + bottom margin flex (8 = NSViewMinYMargin)
    header.setAutoresizingMask_(2 | 8)
    content.addSubview_(header)

    # Outline view inside scroll view
    scroll_y = margin + btn_h + 16 + btn_h + 8
    scroll_h = win_h - margin - 30 - scroll_y
    scroll = NSScrollView.alloc().initWithFrame_(
        NSMakeRect(margin, scroll_y, win_w - 2 * margin, scroll_h)
    )
    scroll.setHasVerticalScroller_(True)
    scroll.setBorderType_(2)  # NSBezelBorder
    # Stretches in both dimensions: width (2) + height (16)
    scroll.setAutoresizingMask_(2 | 16)

    outline = NSOutlineView.alloc().initWithFrame_(
        NSMakeRect(0, 0, win_w - 2 * margin - 20, scroll_h)
    )
    column = NSTableColumn.alloc().initWithIdentifier_("name")
    column.setWidth_(win_w - 2 * margin - 40)
    column.headerCell().setStringValue_("Bin Name")
    column.setEditable_(True)
    outline.addTableColumn_(column)
    outline.setOutlineTableColumn_(column)
    outline.setHeaderView_(None)

    data_source = BinTreeDataSource.alloc().init()
    data_source.roots = initial_roots
    controller.data_source = data_source  # Retain to prevent GC
    outline.setDataSource_(data_source)
    outline.setDelegate_(data_source)
    outline.reloadData()

    scroll.setDocumentView_(outline)
    content.addSubview_(scroll)

    controller.outline_view = outline
    controller.data_source = data_source

    # Expand all top-level by default
    for root in initial_roots:
        outline.expandItem_(root)

    # Action buttons row
    btn_y = margin + btn_h + 8
    btn_w = 100

    # Top row of action buttons (stick to bottom of window via autoresize)
    add_top = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin, btn_y, btn_w, btn_h)
    )
    add_top.setTitle_("+ Top Bin")
    add_top.setBezelStyle_(1)
    add_top.setTarget_(controller)
    add_top.setAction_("addTopBinClicked:")
    add_top.setAutoresizingMask_(32)  # Top margin flex = sticks to bottom
    content.addSubview_(add_top)

    add_sub = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin + btn_w + 8, btn_y, btn_w, btn_h)
    )
    add_sub.setTitle_("+ Sub-Bin")
    add_sub.setBezelStyle_(1)
    add_sub.setTarget_(controller)
    add_sub.setAction_("addSubBinClicked:")
    add_sub.setAutoresizingMask_(32)
    content.addSubview_(add_sub)

    rename_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin + (btn_w + 8) * 2, btn_y, btn_w, btn_h)
    )
    rename_btn.setTitle_("Rename")
    rename_btn.setBezelStyle_(1)
    rename_btn.setTarget_(controller)
    rename_btn.setAction_("renameClicked:")
    rename_btn.setAutoresizingMask_(32)
    content.addSubview_(rename_btn)

    delete_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin + (btn_w + 8) * 3, btn_y, btn_w, btn_h)
    )
    delete_btn.setTitle_("Delete")
    delete_btn.setBezelStyle_(1)
    delete_btn.setTarget_(controller)
    delete_btn.setAction_("deleteClicked:")
    delete_btn.setAutoresizingMask_(32)
    content.addSubview_(delete_btn)

    # Bottom row: Revert / Cancel / Save (stick to bottom)
    revert_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(margin, margin, 140, btn_h)
    )
    revert_btn.setTitle_("Revert to Default")
    revert_btn.setBezelStyle_(1)
    revert_btn.setTarget_(controller)
    revert_btn.setAction_("revertToDefaultClicked:")
    revert_btn.setAutoresizingMask_(32)
    content.addSubview_(revert_btn)

    # Save / Cancel buttons (bottom right) — stick to right and bottom
    # NSViewMinXMargin=1 (left margin flexes, sticks to right)
    cancel_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(win_w - margin - 200, margin, 90, btn_h)
    )
    cancel_btn.setTitle_("Cancel")
    cancel_btn.setBezelStyle_(1)
    cancel_btn.setTarget_(controller)
    cancel_btn.setAction_("cancelClicked:")
    cancel_btn.setAutoresizingMask_(1 | 32)  # left margin flex + top margin flex (sticks bottom-right)
    content.addSubview_(cancel_btn)

    save_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(win_w - margin - 100, margin, 90, btn_h)
    )
    save_btn.setTitle_("Save")
    save_btn.setBezelStyle_(1)
    save_btn.setKeyEquivalent_("\r")
    save_btn.setAutoresizingMask_(1 | 32)
    save_btn.setTarget_(controller)
    save_btn.setAction_("saveClicked:")
    content.addSubview_(save_btn)

    # Show window (non-modal so it's a real popout)
    window.makeKeyAndOrderFront_(None)
    NSApp.activateIgnoringOtherApps_(True)

    # Retain controller and window in module-level list to prevent GC
    _RETAINED.append((controller, window, data_source))
