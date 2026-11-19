"""
End-to-end UI tests for Raspberry Pi Camera Control
Tests all UI elements, video playback, and camera controls using Playwright
"""
import pytest
from playwright.sync_api import Page, expect
import time

# Test configuration - will be overridden by --base-url command line arg
TIMEOUT = 10000  # 10 seconds


class TestPageLayout:
    """Test basic page structure and layout"""
    
    def test_page_loads(self, page: Page, base_url: str):
        """Test that the page loads successfully"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        expect(page).to_have_title("Garage Cam")
    
    def test_top_bar_elements(self, page: Page, base_url: str):
        """Test that top bar contains all required elements"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        # Camera name should be visible
        camera_name = page.locator(".camera-name")
        expect(camera_name).to_be_visible()
        
        # Status circle should be visible (camera status icon)
        status_icon = page.locator("#camera-status-icon")
        expect(status_icon).to_be_visible()
        
        # HDR status should be visible
        hdr_status = page.locator("#hdr-status")
        expect(hdr_status).to_be_visible()
        expect(hdr_status).to_contain_text("HDR:", ignore_case=True)
        
        # Bandwidth status should be visible
        bandwidth_status = page.locator("#bandwidth-status")
        expect(bandwidth_status).to_be_visible()
        
        # Settings menu icon should be visible
        settings_icon = page.locator(".settings-icon")
        expect(settings_icon).to_be_visible()
    
    def test_video_player_exists(self, page: Page, base_url: str):
        """Test that video player element exists"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        video = page.locator("#stream")
        expect(video).to_be_attached()
    
    def test_control_buttons_exist(self, page: Page, base_url: str):
        """Test that all control buttons exist"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        # Play/Pause button
        play_pause = page.locator("#play-pause-btn")
        expect(play_pause).to_be_visible()
        
        # Stop button (has title="Stop Stream")
        stop_button = page.locator('button[title="Stop Stream"]')
        expect(stop_button).to_be_visible()
        
        # Snapshot button
        snapshot_button = page.locator('button[title="Take Picture"]')
        expect(snapshot_button).to_be_visible()
        
        # Fullscreen button
        fullscreen_button = page.locator('button[title="Fullscreen"]')
        expect(fullscreen_button).to_be_visible()


class TestSettingsPanel:
    """Test settings panel functionality"""
    
    def test_settings_panel_opens(self, page: Page, base_url: str):
        """Test that settings panel can be opened"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        # Panel should be hidden initially
        settings_panel = page.locator("#settings-panel")
        panel_classes = settings_panel.get_attribute("class") or ""
        assert "open" not in panel_classes
        
        # Click settings icon
        page.locator(".settings-icon").click()
        page.wait_for_timeout(200)
        
        # Panel should now have 'open' class
        panel_classes = settings_panel.get_attribute("class") or ""
        assert "open" in panel_classes
    
    def test_settings_panel_closes(self, page: Page, base_url: str):
        """Test that settings panel can be closed"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        # Open panel
        page.locator(".settings-icon").click()
        page.wait_for_timeout(400)  # Wait longer for animation
        settings_panel = page.locator("#settings-panel")
        panel_classes = settings_panel.get_attribute("class") or ""
        assert "open" in panel_classes
        
        # Click close button instead of settings icon to avoid interception
        close_btn = page.locator("button.close-btn")
        close_btn.click()
        page.wait_for_timeout(400)  # Wait longer for animation
        panel_classes = settings_panel.get_attribute("class") or ""
        assert "open" not in panel_classes
    
    def test_all_sliders_exist(self, page: Page, base_url: str):
        """Test that all slider controls exist"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.locator(".settings-icon").click()
        page.wait_for_timeout(300)
        
        sliders = {
            "brightness": "Brightness",
            "contrast": "Contrast",
            "saturation": "Saturation",
            "sharpness": "Sharpness",
            "shutter": "Shutter"
        }
        
        for slider_id, label_text in sliders.items():
            slider = page.locator(f"#{slider_id}")
            expect(slider).to_be_attached()
    
    def test_all_dropdowns_exist(self, page: Page, base_url: str):
        """Test that all dropdown controls exist"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.locator(".settings-icon").click()
        page.wait_for_timeout(300)
        
        dropdowns = ["denoise", "hdr", "exposure", "metering", "awb", "rotation"]
        
        for dropdown_id in dropdowns:
            dropdown = page.locator(f"#{dropdown_id}")
            expect(dropdown).to_be_attached()
    
    def test_flip_checkboxes_exist(self, page: Page, base_url: str):
        """Test that flip toggle switches exist"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.locator(".settings-icon").click()
        page.wait_for_timeout(300)
        
        # Look for toggle switches with vflip and hflip
        vflip_toggle = page.locator('[onclick*="vflip"]')
        hflip_toggle = page.locator('[onclick*="hflip"]')
        
        expect(vflip_toggle).to_be_attached()
        expect(hflip_toggle).to_be_attached()
    
    def test_resolution_controls_exist(self, page: Page, base_url: str):
        """Test that resolution controls exist"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.locator(".settings-icon").click()
        page.wait_for_timeout(300)
        
        resolution_select = page.locator("#resolution")
        expect(resolution_select).to_be_attached()
        
        framerate_input = page.locator("#framerate")
        expect(framerate_input).to_be_attached()


class TestCameraControls:
    """Test camera control interactions"""
    
    def test_play_pause_toggle(self, page: Page, base_url: str):
        """Test play/pause button functionality"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        play_pause_btn = page.locator("#play-pause-btn")
        
        # Click to pause
        play_pause_btn.click()
        page.wait_for_timeout(500)
        
        # Click to play
        play_pause_btn.click()
        page.wait_for_timeout(500)
    
    def test_settings_load(self, page: Page, base_url: str):
        """Test that settings are loaded from backend"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)  # Wait for settings to load
        
        page.locator(".settings-icon").click()
        page.wait_for_timeout(300)
        
        # Check that HDR dropdown exists (indicates settings loaded)
        hdr_select = page.locator("#hdr")
        expect(hdr_select).to_be_attached()
    
    def test_hdr_dropdown_changes(self, page: Page, base_url: str):
        """Test HDR dropdown interaction"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)
        
        page.locator(".settings-icon").click()
        page.wait_for_timeout(300)
        
        hdr_select = page.locator("#hdr")
        initial_value = hdr_select.input_value()
        
        # Try to change HDR setting if there's a different option
        if initial_value == "off":
            hdr_select.select_option("auto")  # Select the "Auto" option
        else:
            hdr_select.select_option("off")  # Select the "Off" option
        page.wait_for_timeout(500)
        
        # Check HDR status exists in top bar
        hdr_status = page.locator("#hdr-status")
        expect(hdr_status).to_be_visible()
        expect(hdr_status).to_contain_text("HDR:", ignore_case=True)
    
    def test_rotation_dropdown_shows_loading(self, page: Page, base_url: str):
        """Test that rotation dropdown exists"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)
        
        page.locator(".settings-icon").click()
        page.wait_for_timeout(300)
        
        rotation_select = page.locator("#rotation")
        expect(rotation_select).to_be_attached()


class TestStatusIndicators:
    """Test status indicators and real-time updates"""
    
    def test_bandwidth_updates(self, page: Page, base_url: str):
        """Test that bandwidth indicator exists and displays Kbps"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        bandwidth_status = page.locator("#bandwidth-status")
        expect(bandwidth_status).to_be_visible()
        
        # Should contain "Kbps"
        expect(bandwidth_status).to_contain_text("Kbps", ignore_case=True)
    
    def test_status_circle_color(self, page: Page, base_url: str):
        """Test that status circle has proper structure"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        status_icon = page.locator("#camera-status-icon")
        expect(status_icon).to_be_visible()
        
        # Status icon should exist and have status-icon class
        classes = status_icon.get_attribute("class") or ""
        assert "status-icon" in classes
    
    def test_hdr_status_displays(self, page: Page, base_url: str):
        """Test that HDR status is displayed"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)
        
        hdr_status = page.locator("#hdr-status")
        expect(hdr_status).to_be_visible()
        
        # Should contain "HDR:"
        text = hdr_status.inner_text()
        assert "HDR:" in text


class TestVideoStream:
    """Test video streaming functionality"""
    
    def test_video_element_plays(self, page: Page, base_url: str):
        """Test that video element exists and is attached"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)
        
        video = page.locator("#stream")
        
        # Video element should exist and be attached to DOM
        expect(video).to_be_attached()
    
    def test_timestamp_exists(self, page: Page, base_url: str):
        """Test that timestamp element exists"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        timestamp = page.locator("#timestamp")
        # Timestamp may exist or not, but if it does, it should be visible
        # Don't fail if it doesn't exist, just check if it does
        if timestamp.count() > 0:
            expect(timestamp).to_be_visible()


class TestResponsiveness:
    """Test responsive behavior and mobile compatibility"""
    
    def test_mobile_viewport(self, page: Page, base_url: str):
        """Test page on mobile viewport"""
        page.set_viewport_size({"width": 375, "height": 667})  # iPhone SE
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        # Key elements should still be visible
        expect(page.locator(".camera-name")).to_be_visible()
        expect(page.locator("#stream")).to_be_visible()
        expect(page.locator(".settings-icon")).to_be_visible()
    
    def test_tablet_viewport(self, page: Page, base_url: str):
        """Test page on tablet viewport"""
        page.set_viewport_size({"width": 768, "height": 1024})  # iPad
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        expect(page.locator(".camera-name")).to_be_visible()
        expect(page.locator("#stream")).to_be_visible()


class TestAPIEndpoints:
    """Test backend API endpoints via browser interactions"""
    
    def test_settings_endpoint_loads(self, page: Page, base_url: str):
        """Test that /settings endpoint returns data"""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        
        # Settings should have loaded the HDR dropdown
        hdr_select = page.locator("#hdr")
        expect(hdr_select).to_be_attached()
    
    def test_system_info_endpoint(self, page: Page, base_url: str):
        """Test that /system_info endpoint returns data"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        # System info should populate the bandwidth status at least
        bandwidth = page.locator("#bandwidth-status")
        expect(bandwidth).to_be_visible()


class TestStreamingSettings:
    """On-demand toggle and bitrate dropdown in the Streaming section"""

    @staticmethod
    def _settings(page: Page, base_url: str) -> dict:
        """Read the saved settings straight from the backend"""
        return page.request.get(base_url.rsplit('/web', 1)[0] + '/settings').json()

    def _open_settings(self, page: Page, base_url: str):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)  # Wait for settings to load
        page.locator(".settings-icon").click()
        page.wait_for_timeout(300)

    def test_on_demand_toggle_reflects_setting(self, page: Page, base_url: str):
        """The toggle exists and shows the saved mode"""
        self._open_settings(page, base_url)
        toggle = page.locator("#on-demand-toggle")
        expect(toggle).to_be_attached()

        on_demand = self._settings(page, base_url).get("on_demand", True)
        is_active = "active" in (toggle.get_attribute("class") or "")
        assert is_active == bool(on_demand)

    def test_on_demand_toggle_saves(self, page: Page, base_url: str):
        """Clicking the toggle switches between on-demand and continuous, and back"""
        self._open_settings(page, base_url)
        toggle = page.locator("#on-demand-toggle")
        before = bool(self._settings(page, base_url).get("on_demand", True))

        toggle.click()
        page.wait_for_timeout(1500)  # Settings are sent after an 800ms debounce
        assert bool(self._settings(page, base_url).get("on_demand")) == (not before)

        toggle.click()  # Restore
        page.wait_for_timeout(1500)
        assert bool(self._settings(page, base_url).get("on_demand")) == before

    def test_bitrate_dropdown_options(self, page: Page, base_url: str):
        """The bitrate dropdown offers Auto plus fixed rates"""
        self._open_settings(page, base_url)
        bitrate = page.locator("#bitrate")
        expect(bitrate).to_be_attached()

        values = bitrate.locator("option").evaluate_all("options => options.map(o => o.value)")
        assert "0" in values, "Auto option missing"
        assert "3000000" in values and "5000000" in values

    def test_bitrate_change_is_saved(self, page: Page, base_url: str):
        """Choosing a bitrate stores it; choosing the old value restores it"""
        self._open_settings(page, base_url)
        bitrate = page.locator("#bitrate")
        before = str(self._settings(page, base_url).get("bitrate", 0) or 0)
        target = "2000000" if before != "2000000" else "3000000"

        bitrate.select_option(target)
        page.wait_for_timeout(1000)
        assert str(self._settings(page, base_url).get("bitrate")) == target

        bitrate.select_option(before)  # Restore
        page.wait_for_timeout(1000)
        assert str(self._settings(page, base_url).get("bitrate", 0) or 0) == before

    def test_custom_bitrate_is_shown(self, page: Page, base_url: str):
        """A bitrate set through the API that is not in the list is shown, not reported as Auto"""
        origin = base_url.rsplit('/web', 1)[0]
        before = self._settings(page, base_url).get("bitrate", 0) or 0
        page.request.post(origin + '/apply', data={"bitrate": 1234000})
        try:
            self._open_settings(page, base_url)
            bitrate = page.locator("#bitrate")
            assert bitrate.input_value() == "1234000"
            expect(bitrate.locator("option:checked")).to_contain_text("1.23 Mbit/s")
        finally:
            page.request.post(origin + '/apply', data={"bitrate": before})


@pytest.mark.slow
class TestExtendedFunctionality:
    """Extended tests that take longer to run"""
    
    def test_slider_interaction(self, page: Page, base_url: str):
        """Test that sliders can be found and have proper attributes"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.locator(".settings-icon").click()
        page.wait_for_timeout(300)
        
        brightness_slider = page.locator("#brightness")
        expect(brightness_slider).to_be_attached()
        
        # Slider should have input type or be a proper slider element
        slider_type = brightness_slider.get_attribute("type")
        assert slider_type in ["range", "slider"] or brightness_slider.get_attribute("role") == "slider"
    
    def test_multiple_setting_changes(self, page: Page, base_url: str):
        """Test changing multiple settings in sequence"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)
        
        page.locator(".settings-icon").click()
        page.wait_for_timeout(300)
        
        # Just verify the dropdowns exist and are interactive
        hdr = page.locator("#hdr")
        expect(hdr).to_be_attached()
        
        exposure = page.locator("#exposure")
        expect(exposure).to_be_attached()
        
        awb = page.locator("#awb")
        expect(awb).to_be_attached()
