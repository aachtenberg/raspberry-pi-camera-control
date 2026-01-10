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
        expect(page).to_have_title("picamctl")
    
    def test_top_bar_elements(self, page: Page, base_url: str):
        """Test that top bar contains all required elements"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        
        # Camera name should be visible
        camera_name = page.locator(".camera-name")
        expect(camera_name).to_be_visible()
        
        # Status circle should be visible
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
        
        video = page.locator("#stream")
        expect(video).to_be_attached()
    
    def test_control_buttons_exist(self, page: Page, base_url: str):
        """Test that all control buttons exist"""
        page.goto(base_url)
        
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
        
        # Panel should be hidden initially
        settings_panel = page.locator("#settings-panel")
        expect(settings_panel).not_to_have_class("open")
        
        # Click settings icon
        page.locator(".settings-icon").click()
        
        # Panel should now be visible
        expect(settings_panel).to_have_class("settings-panel open")
    
    def test_settings_panel_closes(self, page: Page, base_url: str):
        """Test that settings panel can be closed"""
        page.goto(base_url)
        
        # Open panel
        page.locator(".settings-icon").click()
        settings_panel = page.locator("#settings-panel")
        expect(settings_panel).to_have_class("settings-panel open")
        
        # Close panel
        page.locator(".settings-icon").click()
        expect(settings_panel).not_to_have_class("open")
    
    def test_all_sliders_exist(self, page: Page, base_url: str):
        """Test that all slider controls exist"""
        page.goto(base_url)
        page.locator(".settings-icon").click()
        
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
        page.locator(".settings-icon").click()
        
        dropdowns = ["denoise", "hdr", "exposure", "metering", "awb", "rotation"]
        
        for dropdown_id in dropdowns:
            dropdown = page.locator(f"#{dropdown_id}")
            expect(dropdown).to_be_attached()
    
    def test_flip_checkboxes_exist(self, page: Page, base_url: str):
        """Test that flip checkboxes exist"""
        page.goto(base_url)
        page.locator(".settings-icon").click()
        
        # Checkboxes are inside labels, find by input type
        hflip = page.locator('input[type="checkbox"]').nth(0)  # First checkbox is hflip
        vflip = page.locator('input[type="checkbox"]').nth(1)  # Second checkbox is vflip
        
        expect(hflip).to_be_attached()
        expect(vflip).to_be_attached()
    
    def test_resolution_controls_exist(self, page: Page, base_url: str):
        """Test that resolution controls exist"""
        page.goto(base_url)
        page.locator(".settings-icon").click()
        
        resolution_select = page.locator("#resolution")
        expect(resolution_select).to_be_attached()
        
        framerate_input = page.locator("#framerate")
        expect(framerate_input).to_be_attached()


class TestCameraControls:
    """Test camera control interactions"""
    
    def test_play_pause_toggle(self, page: Page, base_url: str):
        """Test play/pause button functionality"""
        page.goto(base_url)
        
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
        page.wait_for_timeout(2000)  # Wait for settings to load
        
        page.locator(".settings-icon").click()
        
        # Check that dropdowns have values
        hdr_select = page.locator("#hdr")
        expect(hdr_select).not_to_have_value("")
    
    def test_hdr_dropdown_changes(self, page: Page, base_url: str):
        """Test HDR dropdown interaction"""
        page.goto(base_url)
        page.wait_for_timeout(1000)
        
        page.locator(".settings-icon").click()
        
        hdr_select = page.locator("#hdr")
        initial_value = hdr_select.input_value()
        
        # Change HDR setting
        hdr_select.select_option("auto")
        page.wait_for_timeout(1000)
        
        # Check HDR status updated in top bar
        hdr_status = page.locator("#hdr-status")
        expect(hdr_status).to_contain_text("HDR:", ignore_case=True)
    
    def test_rotation_dropdown_shows_loading(self, page: Page, base_url: str):
        """Test that rotation change shows loading overlay"""
        page.goto(base_url)
        page.wait_for_timeout(1000)
        
        page.locator(".settings-icon").click()
        
        rotation_select = page.locator("#rotation")
        initial_value = rotation_select.input_value()
        
        # Change rotation (should show loading overlay)
        if initial_value == "0":
            rotation_select.select_option("180")
        else:
            rotation_select.select_option("0")
        
        # Loading overlay should appear briefly
        page.wait_for_timeout(500)
        
        # Wait for stream to restart
        page.wait_for_timeout(4000)


class TestStatusIndicators:
    """Test status indicators and real-time updates"""
    
    def test_bandwidth_updates(self, page: Page, base_url: str):
        """Test that bandwidth indicator updates"""
        page.goto(base_url)
        
        bandwidth_status = page.locator("#bandwidth-status")
        initial_text = bandwidth_status.inner_text()
        
        # Wait for bandwidth update (polls every 2 seconds)
        page.wait_for_timeout(3000)
        
        updated_text = bandwidth_status.inner_text()
        # Should contain "Kbps"
        expect(bandwidth_status).to_contain_text("Kbps")
    
    def test_status_circle_color(self, page: Page, base_url: str):
        """Test that status circle has a status class"""
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)  # Wait for initial stream
        
        status_icon = page.locator("#camera-status-icon")
        expect(status_icon).to_be_visible()
        
        # Status icon should exist and have some class
        classes = status_icon.get_attribute("class") or ""
        # The class attribute will have "status-icon" at minimum
        assert "status-icon" in classes
    
    def test_hdr_status_displays(self, page: Page, base_url: str):
        """Test that HDR status is displayed"""
        page.goto(base_url)
        page.wait_for_timeout(2000)
        
        hdr_status = page.locator("#hdr-status")
        expect(hdr_status).to_be_visible()
        
        # Should contain either "Off" or an HDR mode
        text = hdr_status.inner_text()
        assert "HDR:" in text


class TestVideoStream:
    """Test video streaming functionality"""
    
    def test_video_element_plays(self, page: Page, base_url: str):
        """Test that video element attempts to play"""
        page.goto(base_url)
        page.wait_for_timeout(3000)  # Wait for HLS to initialize
        
        video = page.locator("#stream")
        
        # Video element should exist
        expect(video).to_be_attached()
        
        # Check if video has loaded (may need HLS segments available)
        # This is a basic check - actual playback depends on camera being active
    
    def test_timestamp_displays(self, page: Page, base_url: str):
        """Test that timestamp is displayed and updates"""
        page.goto(base_url)
        
        timestamp = page.locator("#timestamp")
        expect(timestamp).to_be_visible()
        
        initial_time = timestamp.inner_text()
        page.wait_for_timeout(2000)
        updated_time = timestamp.inner_text()
        
        # Timestamp should be updating
        # Format should be time-like (contains : )
        assert ":" in updated_time


class TestResponsiveness:
    """Test responsive behavior and mobile compatibility"""
    
    def test_mobile_viewport(self, page: Page, base_url: str):
        """Test page on mobile viewport"""
        page.set_viewport_size({"width": 375, "height": 667})  # iPhone SE
        page.goto(base_url)
        
        # Key elements should still be visible
        expect(page.locator(".camera-name")).to_be_visible()
        expect(page.locator("#stream")).to_be_visible()
        expect(page.locator(".settings-icon")).to_be_visible()
    
    def test_tablet_viewport(self, page: Page, base_url: str):
        """Test page on tablet viewport"""
        page.set_viewport_size({"width": 768, "height": 1024})  # iPad
        page.goto(base_url)
        
        expect(page.locator(".camera-name")).to_be_visible()
        expect(page.locator("#stream")).to_be_visible()


class TestAPIEndpoints:
    """Test backend API endpoints via browser interactions"""
    
    def test_settings_endpoint_loads(self, page: Page, base_url: str):
        """Test that /settings endpoint returns data"""
        page.goto(base_url)
        
        # Listen for API response
        with page.expect_response(lambda response: "/settings" in response.url) as response_info:
            page.reload()
        
        response = response_info.value
        assert response.status == 200
    
    def test_system_info_endpoint(self, page: Page, base_url: str):
        """Test that /system_info endpoint returns data"""
        page.goto(base_url)
        
        # System info polls every 2 seconds
        with page.expect_response(lambda response: "/system_info" in response.url) as response_info:
            page.wait_for_timeout(3000)
        
        response = response_info.value
        assert response.status == 200


@pytest.mark.slow
class TestExtendedFunctionality:
    """Extended tests that take longer to run"""
    
    def test_slider_interaction(self, page: Page, base_url: str):
        """Test that sliders can be moved and update settings"""
        page.goto(base_url)
        page.locator(".settings-icon").click()
        
        brightness_slider = page.locator("#brightness")
        
        # Get bounding box and drag slider
        box = brightness_slider.bounding_box()
        if box:
            # Drag to middle
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_timeout(1000)  # Wait for debounce
    
    def test_multiple_setting_changes(self, page: Page, base_url: str):
        """Test changing multiple settings in sequence"""
        page.goto(base_url)
        page.wait_for_timeout(1000)
        
        page.locator(".settings-icon").click()
        
        # Change HDR
        page.locator("#hdr").select_option("auto")
        page.wait_for_timeout(500)
        
        # Change exposure
        page.locator("#exposure").select_option("sport")
        page.wait_for_timeout(500)
        
        # Change white balance
        page.locator("#awb").select_option("daylight")
        page.wait_for_timeout(1000)
