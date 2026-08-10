from app.integrations.browser_actions import BrowserActions


def test_youtube_url_is_encoded():
    url = BrowserActions.youtube_search("lofi hip hop")
    assert "youtube.com/results" in url
    assert "lofi+hip+hop" in url


def test_google_maps_url_is_encoded():
    url = BrowserActions.google_maps("coffee near me")
    assert "google.com/maps/search" in url
    assert "coffee+near+me" in url
