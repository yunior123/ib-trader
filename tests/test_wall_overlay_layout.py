from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "charts" / "live.html").read_text(
    encoding="utf-8"
)


def test_wall_labels_use_screen_coordinate_collision_packing():
    assert "function packBubbleRows(items, minGap, top, bottom)" in HTML
    assert "packBubbleRows(visible, 31 * vr" in HTML
    assert "item.anchorY" in HTML and "item.drawY" in HTML
    assert "ctx.lineTo(x0 + 13 * hr, yb)" in HTML


def test_native_wall_chips_are_replaced_by_mini_tags_when_bricks_are_off():
    assert "let packedWallLabelsOn = true" in HTML
    assert "axisLabelVisible: axisLabel && !hover" in HTML
    assert "if (packedWallLabelsOn || !levelHoverRows.length) return" in HTML
    assert "!packedWallLabelsOn" in HTML
    assert "packedWallLabelsOn = !!on" in HTML


def test_bricks_default_off_and_structural_line_widths_carry_hierarchy():
    assert 'localStorage.getItem("gexBubbles_v2") === "1"' in HTML
    assert "catch (e) { return false; }" in HTML
    assert "!packedWallLabelsOn, 4," in HTML
    assert "!packedWallLabelsOn, 2," in HTML
    assert "Math.max(3, wallW(wallIntensity" in HTML
    london_hide = HTML.split("function applyLondonOnlyUi(on)", 1)[1].split("function chartAge", 1)[0]
    assert '"bubblebar"' not in london_hide


def test_london_magnet_uses_live_magnet_field_and_marks_coincident_wall():
    assert "lv.magnet != null ? lv.magnet : lv.abs_wall" in HTML
    assert "lv.magnet_gamma_volume != null" in HTML
    assert 'magOnCall ? "C·M" : "C"' in HTML
    assert 'magOnPut ? "P·M" : "P"' in HTML
    assert "if (magPrice != null && !magOnCall && !magOnPut)" in HTML


def test_default_structural_axis_tags_are_tiny_and_details_move_to_hover():
    assert '"rgba(244,196,48,0.85)", "F"' in HTML
    assert '"rgba(255,140,60,0.86)", "A"' in HTML
    assert '"rgba(255,179,0,0.72)", "M"' in HTML
    assert 'const tiny = name.startsWith("CW") ? "C"' in HTML
    assert 'name.startsWith("PW") ? "P"' in HTML
    structural = HTML.split("function drawLevels(lv)", 1)[1].split("wallBub.setLevels(lv)", 1)[0]
    assert '" Γvol " + fmtM' not in structural
    assert "FLIP · Dealer gamma zero-crossing" in structural
    assert "A-FLIP · Activity zero-crossing" in structural


def test_structural_boxes_are_custom_translucent_tags_not_opaque_native_labels():
    assert 'id="leveltags"' in HTML
    assert "axisLabelVisible: axisLabel && !hover" in HTML
    assert 'tag.style.background = levelTagColor(r.color, 0.24)' in HTML
    assert 'tag.style.borderColor = levelTagColor(r.color, 0.72)' in HTML
    assert 'tag.textContent = r.tag' in HTML
    assert 'right:53px' in HTML


def test_gamma_wall_bars_and_numbers_render_above_structural_lines():
    gex = HTML.split("class GexView", 1)[1].split("class GexProfile", 1)[0]
    assert 'zOrder() { return "top"; }' in gex
    assert 'ctx.font = `700 ${10 * vr}px' in gex
    assert 'ctx.fillStyle = "rgba(12,16,24,0.90)"' in gex
    assert '"rgba(255,213,79,1)"' in gex


def test_packed_labels_have_an_opaque_high_contrast_chip():
    assert 'ctx.fillStyle = "rgba(8,12,20,0.92)"' in HTML
    assert "ctx.strokeRect(xEnd - 4 * hr" in HTML
    assert "ctx.font = `700 " in HTML
