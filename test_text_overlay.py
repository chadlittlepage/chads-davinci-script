"""Test script: Add text overlay to REEL SOURCE (V2) via Fusion comp.

Temporarily disables all other video tracks so the Fusion page opens
the correct clip, adds a TextPlus node, then re-enables everything.

Run with: PYTHONPATH=src python3 test_text_overlay.py
"""

import sys
import time

sys.path.append(
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
)
import DaVinciResolveScript as dvr


def add_text_to_track(resolve, timeline, track_num, text_label):
    """Add a TextPlus overlay to a specific video track's clip.

    Disables all other tracks so Fusion opens the correct clip,
    adds text, then re-enables everything.
    """
    track_name = timeline.GetTrackName("video", track_num)
    clips = timeline.GetItemListInTrack("video", track_num)
    if not clips:
        print(f"  ERROR: No clips on V{track_num} ({track_name})")
        return False

    clip = clips[0]
    print(f"  V{track_num} ({track_name}): '{clip.GetName()}' frames {clip.GetStart()}-{clip.GetEnd()}")

    total_tracks = timeline.GetTrackCount("video")

    # Save current enable state of all tracks
    saved_states = {}
    for t in range(1, total_tracks + 1):
        saved_states[t] = timeline.GetIsTrackEnabled("video", t)

    # Disable ALL tracks except our target
    for t in range(1, total_tracks + 1):
        if t == track_num:
            timeline.SetTrackEnable("video", t, True)
        else:
            timeline.SetTrackEnable("video", t, False)

    # Position playhead over the clip
    timeline.SetCurrentTimecode(timeline.GetStartTimecode())
    time.sleep(0.3)

    # Switch to Fusion — should now open our target clip's comp
    resolve.OpenPage("fusion")
    time.sleep(1.5)

    fusion = resolve.Fusion()
    comp = fusion.GetCurrentComp()
    if comp is None:
        print(f"  ERROR: No Fusion comp for V{track_num}")
        resolve.OpenPage("edit")
        # Restore track states
        for t, state in saved_states.items():
            timeline.SetTrackEnable("video", t, state)
        return False

    # Verify this is a clean comp (MediaIn + MediaOut only)
    tools = comp.GetToolList()
    tool_ids = [tools[k].GetAttrs().get("TOOLS_RegID", "") for k in tools]
    print(f"  Fusion comp tools: {tool_ids}")

    if "TextPlus" in tool_ids:
        print(f"  SKIP: Text already added to V{track_num}")
        resolve.OpenPage("edit")
        for t, state in saved_states.items():
            timeline.SetTrackEnable("video", t, state)
        return True

    # Find MediaIn and MediaOut
    media_in = comp.FindTool("MediaIn1")
    media_out = comp.FindTool("MediaOut1")
    if not media_in or not media_out:
        print(f"  ERROR: Missing MediaIn/MediaOut")
        resolve.OpenPage("edit")
        for t, state in saved_states.items():
            timeline.SetTrackEnable("video", t, state)
        return False

    # Add TextPlus
    text_tool = comp.AddTool("TextPlus", -32768, -32768)
    if not text_tool:
        print(f"  ERROR: Could not add TextPlus")
        resolve.OpenPage("edit")
        for t, state in saved_states.items():
            timeline.SetTrackEnable("video", t, state)
        return False

    # Set text content
    text_tool.SetInput("StyledText", text_label)

    # Position: lower-right of the 1920x1080 clip frame.
    # The timeline-level quad transform will move it to the correct
    # quadrant automatically.
    text_tool.SetInput("Center", [0.85, 0.08])

    # Font: Open Sans Regular, small size
    text_tool.SetInput("Font", "Open Sans")
    text_tool.SetInput("Style", "Regular")
    text_tool.SetInput("Size", 0.032)

    # White text
    text_tool.SetInput("Red1", 1.0)
    text_tool.SetInput("Green1", 1.0)
    text_tool.SetInput("Blue1", 1.0)
    text_tool.SetInput("Alpha1", 1.0)

    # Add Merge: MediaIn -> BG, TextPlus -> FG -> MediaOut
    merge = comp.AddTool("Merge", -32768, -32768)
    if merge:
        merge.ConnectInput("Background", media_in)
        merge.ConnectInput("Foreground", text_tool)
        media_out.ConnectInput("Input", merge)
        print(f"  Text '{text_label}' added to V{track_num} — lower-right of clip frame")
    else:
        print(f"  WARNING: Merge failed, text node added but not wired")

    # Back to Edit and restore track states
    resolve.OpenPage("edit")
    time.sleep(0.3)
    for t, state in saved_states.items():
        timeline.SetTrackEnable("video", t, state)

    return True


def main():
    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        print("ERROR: Cannot connect to DaVinci Resolve.")
        sys.exit(1)

    project = resolve.GetProjectManager().GetCurrentProject()
    timeline = project.GetCurrentTimeline()

    print(f"Project: {project.GetName()}")
    print(f"Timeline: {timeline.GetName()}")
    print(f"Tracks: {timeline.GetTrackCount('video')}")

    # Test with V2 REEL SOURCE only
    TARGET_TRACK = 2
    TEXT_LABEL = "REEL SOURCE"

    print(f"\n--- Adding text overlay to V{TARGET_TRACK} ---")
    ok = add_text_to_track(resolve, timeline, TARGET_TRACK, TEXT_LABEL)

    if ok:
        # Verify clip position
        clips = timeline.GetItemListInTrack("video", TARGET_TRACK)
        if clips:
            c = clips[0]
            print(f"\n  Video after: frames {c.GetStart()}-{c.GetEnd()} — position unchanged")
        print("\nSUCCESS — check V2 in Resolve.")
    else:
        print("\nFAILED — see errors above.")


if __name__ == "__main__":
    main()
