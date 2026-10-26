"""Tests for Siemens Energy platform date filtering."""

import pytest
from datetime import date, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.webscraper.platforms.siemens import SiemensEnergyPlatform, SIEMENS_BASE_URL


class TestSiemensDateFiltering:
    """Tests for Siemens Energy 7-day date filtering."""

    @pytest.fixture(autouse=True)
    def fixed_today(self, monkeypatch):
        class FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 9, 4)
        monkeypatch.setattr("src.webscraper.platforms.siemens.date", FixedDate)

    def setup_method(self):
        self.platform = SiemensEnergyPlatform()
        self.site_config = {
            "company": "Siemens Energy",
            "search_url": "https://jobs.siemens-energy.com/en_US/jobs/Jobs",
            "search_term": "",
            "max_results": 10,
            "country_filter": "964485",
            "posted_within_days": 7,
        }
        self.site_config_no_filter = {
            "company": "Siemens Energy",
            "search_url": "https://jobs.siemens-energy.com/en_US/jobs/Jobs",
            "search_term": "",
            "max_results": 10,
            "country_filter": "964485",
        }

    def test_extract_date_posted_valid_format(self):
        """Test _extract_date_posted converts '4-Sep-2026' to '2026-09-04'."""
        from bs4 import BeautifulSoup
        html = '<meta name="Description" content="Job Title at created  4-Sep-2026">'
        soup = BeautifulSoup(html, "html.parser")
        result = self.platform._extract_date_posted(soup, {})
        assert result == "2026-09-04"

    def test_extract_date_posted_invalid_format(self):
        """Test _extract_date_posted returns None for malformed dates (regex doesn't match)."""
        from bs4 import BeautifulSoup
        html = '<meta name="Description" content="Job Title at created  invalid-date">'
        soup = BeautifulSoup(html, "html.parser")
        result = self.platform._extract_date_posted(soup, {})
        assert result is None

    def test_extract_date_posted_missing_meta(self):
        """Test _extract_date_posted returns None when meta tag missing."""
        from bs4 import BeautifulSoup
        html = '<html><body>No meta tag</body></html>'
        soup = BeautifulSoup(html, "html.parser")
        result = self.platform._extract_date_posted(soup, {})
        assert result is None

    @patch("src.webscraper.platforms.siemens.requests.Session")
    def test_recent_job_included(self, mock_session_class):
        """Test a job within 7 days is included."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Mock listing page response
        listing_html = """
        <html>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Test-Job/123456">Test Job</a>
                <div class="article__content" data-job-id="123456"></div>
            </article>
        </html>
        """
        # Mock detail page response with recent date
        detail_html = """
        <html>
            <meta name="Description" content="Test Job at created  3-Sep-2026">
            <meta property="og:title" content="Test Job">
            <div class="article__content__view__field posting-location">
                <div class="article__content__view__field__value">Berlin</div>
                <div class="article__content__view__field__value">Germany</div>
            </div>
            <div class="article__content__view__field">
                <div class="article__content__view__field__label">Company:</div>
                <div class="article__content__view__field__value">Siemens Energy, Inc.</div>
            </div>
            <div class="article__content__view__field">
                <div class="article__content__view__field__label">Organization:</div>
                <div class="article__content__view__field__value">Gas Services</div>
            </div>
            <div class="article__content__view__field">
                <div class="article__content__view__field__label">Full / Part time:</div>
                <div class="article__content__view__field__value">Full-time</div>
            </div>
            <div class="article__content__view__field">
                <div class="article__content__view__field__label">Experience Level:</div>
                <div class="article__content__view__field__value">Entry-Level</div>
            </div>
            <article><h3>About the Role</h3><p>Description here</p></article>
        </html>
        """

        mock_listing_resp = Mock()
        mock_listing_resp.text = listing_html
        mock_listing_resp.raise_for_status = Mock()

        mock_detail_resp = Mock()
        mock_detail_resp.text = detail_html
        mock_detail_resp.raise_for_status = Mock()

        mock_session.get.side_effect = [mock_listing_resp, mock_detail_resp]

        with patch("time.sleep", return_value=None):
            results = self.platform.fetch_jobs(self.site_config, max_results=10)

        assert len(results) == 1
        assert results[0]["id"] == "123456"
        assert results[0]["date_posted"] == "2026-09-03"

    @patch("src.webscraper.platforms.siemens.requests.Session")
    def test_old_job_excluded(self, mock_session_class):
        """Test a job older than 7 days is excluded."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        listing_html = """
        <html>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Old-Job/123456">Old Job</a>
                <div class="article__content" data-job-id="123456"></div>
            </article>
        </html>
        """
        # Date is 10 days ago (outside 7-day window)
        detail_html = """
        <html>
            <meta name="Description" content="Old Job at created  26-Aug-2026">
            <meta property="og:title" content="Old Job">
            <div class="article__content__view__field posting-location">
                <div class="article__content__view__field__value">Berlin</div>
            </div>
            <article><h3>About the Role</h3><p>Description</p></article>
        </html>
        """

        mock_listing_resp = Mock()
        mock_listing_resp.text = listing_html
        mock_listing_resp.raise_for_status = Mock()

        mock_detail_resp = Mock()
        mock_detail_resp.text = detail_html
        mock_detail_resp.raise_for_status = Mock()

        mock_session.get.side_effect = [mock_listing_resp, mock_detail_resp]

        with patch("time.sleep", return_value=None):
            results = self.platform.fetch_jobs(self.site_config, max_results=10)

        assert len(results) == 0

    @patch("src.webscraper.platforms.siemens.requests.Session")
    def test_missing_date_excluded_when_filter_active(self, mock_session_class):
        """Test job with missing date_posted is excluded when filter is active."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        listing_html = """
        <html>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/No-Date-Job/123456">No Date Job</a>
                <div class="article__content" data-job-id="123456"></div>
            </article>
        </html>
        """
        # No meta Description tag
        detail_html = """
        <html>
            <meta property="og:title" content="No Date Job">
            <div class="article__content__view__field posting-location">
                <div class="article__content__view__field__value">Berlin</div>
            </div>
            <article><h3>About the Role</h3><p>Description</p></article>
        </html>
        """

        mock_listing_resp = Mock()
        mock_listing_resp.text = listing_html
        mock_listing_resp.raise_for_status = Mock()

        mock_detail_resp = Mock()
        mock_detail_resp.text = detail_html
        mock_detail_resp.raise_for_status = Mock()

        mock_session.get.side_effect = [mock_listing_resp, mock_detail_resp]

        with patch("time.sleep", return_value=None):
            results = self.platform.fetch_jobs(self.site_config, max_results=10)

        assert len(results) == 0

    @patch("src.webscraper.platforms.siemens.requests.Session")
    def test_malformed_date_excluded_when_filter_active(self, mock_session_class):
        """Test job with malformed date_posted is excluded when filter is active."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        listing_html = """
        <html>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Bad-Date-Job/123456">Bad Date Job</a>
                <div class="article__content" data-job-id="123456"></div>
            </article>
        </html>
        """
        # Invalid date format
        detail_html = """
        <html>
            <meta name="Description" content="Bad Date Job at created  not-a-date">
            <meta property="og:title" content="Bad Date Job">
            <div class="article__content__view__field posting-location">
                <div class="article__content__view__field__value">Berlin</div>
            </div>
            <article><h3>About the Role</h3><p>Description</p></article>
        </html>
        """

        mock_listing_resp = Mock()
        mock_listing_resp.text = listing_html
        mock_listing_resp.raise_for_status = Mock()

        mock_detail_resp = Mock()
        mock_detail_resp.text = detail_html
        mock_detail_resp.raise_for_status = Mock()

        mock_session.get.side_effect = [mock_listing_resp, mock_detail_resp]

        with patch("time.sleep", return_value=None):
            results = self.platform.fetch_jobs(self.site_config, max_results=10)

        assert len(results) == 0

    @patch("src.webscraper.platforms.siemens.requests.Session")
    def test_max_results_applied_after_filtering(self, mock_session_class):
        """Test max_results is applied after date filtering."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Create 5 recent jobs
        listing_html = """
        <html>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Job-1/111111">Job 1</a>
                <div class="article__content" data-job-id="111111"></div>
            </article>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Job-2/222222">Job 2</a>
                <div class="article__content" data-job-id="222222"></div>
            </article>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Job-3/333333">Job 3</a>
                <div class="article__content" data-job-id="333333"></div>
            </article>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Job-4/444444">Job 4</a>
                <div class="article__content" data-job-id="444444"></div>
            </article>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Job-5/555555">Job 5</a>
                <div class="article__content" data-job-id="555555"></div>
            </article>
        </html>
        """

        detail_html_template = """
        <html>
            <meta name="Description" content="{title} at created  3-Sep-2026">
            <meta property="og:title" content="{title}">
            <div class="article__content__view__field posting-location">
                <div class="article__content__view__field__value">Berlin</div>
            </div>
            <article><h3>About the Role</h3><p>Description</p></article>
        </html>
        """

        mock_listing_resp = Mock()
        mock_listing_resp.text = listing_html
        mock_listing_resp.raise_for_status = Mock()

        mock_session.get.side_effect = [
            mock_listing_resp,
            Mock(text=detail_html_template.format(title="Job 1"), raise_for_status=Mock()),
            Mock(text=detail_html_template.format(title="Job 2"), raise_for_status=Mock()),
            Mock(text=detail_html_template.format(title="Job 3"), raise_for_status=Mock()),
            Mock(text=detail_html_template.format(title="Job 4"), raise_for_status=Mock()),
            Mock(text=detail_html_template.format(title="Job 5"), raise_for_status=Mock()),
        ]

        with patch("time.sleep", return_value=None):
            results = self.platform.fetch_jobs(self.site_config, max_results=3)

        assert len(results) == 3

    @patch("src.webscraper.platforms.siemens.requests.Session")
    def test_duplicate_ids_ignored(self, mock_session_class):
        """Test duplicate job IDs are ignored."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        listing_html = """
        <html>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Dup-Job/123456">Dup Job</a>
                <div class="article__content" data-job-id="123456"></div>
            </article>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Dup-Job-2/123456">Dup Job 2</a>
                <div class="article__content" data-job-id="123456"></div>
            </article>
        </html>
        """
        detail_html = """
        <html>
            <meta name="Description" content="Dup Job at created  3-Sep-2026">
            <meta property="og:title" content="Dup Job">
            <div class="article__content__view__field posting-location">
                <div class="article__content__view__field__value">Berlin</div>
            </div>
            <article><h3>About the Role</h3><p>Description</p></article>
        </html>
        """

        mock_listing_resp = Mock()
        mock_listing_resp.text = listing_html
        mock_listing_resp.raise_for_status = Mock()

        mock_detail_resp = Mock()
        mock_detail_resp.text = detail_html
        mock_detail_resp.raise_for_status = Mock()

        mock_session.get.side_effect = [mock_listing_resp, mock_detail_resp]

        with patch("time.sleep", return_value=None):
            results = self.platform.fetch_jobs(self.site_config, max_results=10)

        assert len(results) == 1
        assert results[0]["id"] == "123456"

    @patch("src.webscraper.platforms.siemens.requests.Session")
    def test_detail_fetched_once_per_job(self, mock_session_class):
        """Test detail page is fetched only once per examined job."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        listing_html = """
        <html>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Job-1/111111">Job 1</a>
                <div class="article__content" data-job-id="111111"></div>
            </article>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Job-2/222222">Job 2</a>
                <div class="article__content" data-job-id="222222"></div>
            </article>
        </html>
        """

        detail_html = """
        <html>
            <meta name="Description" content="Job at created  3-Sep-2026">
            <meta property="og:title" content="Job">
            <div class="article__content__view__field posting-location">
                <div class="article__content__view__field__value">Berlin</div>
            </div>
            <article><h3>About the Role</h3><p>Description</p></article>
        </html>
        """

        mock_listing_resp = Mock()
        mock_listing_resp.text = listing_html
        mock_listing_resp.raise_for_status = Mock()

        mock_empty_listing_resp = Mock()
        mock_empty_listing_resp.text = "<html><body></body></html>"
        mock_empty_listing_resp.raise_for_status = Mock()

        mock_detail_resp = Mock()
        mock_detail_resp.text = detail_html
        mock_detail_resp.raise_for_status = Mock()

        # 1st listing + 2 details + 2nd listing (empty) = 4 calls
        mock_session.get.side_effect = [
            mock_listing_resp, mock_detail_resp, mock_detail_resp, mock_empty_listing_resp
        ]

        with patch("time.sleep", return_value=None):
            results = self.platform.fetch_jobs(self.site_config, max_results=10)

        assert len(results) == 2
        # Should only call detail twice (once per unique job)
        assert mock_session.get.call_count == 4  # 1st listing + 2 details + 2nd listing (empty)

    @patch("src.webscraper.platforms.siemens.requests.Session")
    def test_no_filter_returns_all_jobs(self, mock_session_class):
        """Test without posted_within_days, all jobs are returned unfiltered."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        listing_html = """
        <html>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Recent-Job/111111">Recent Job</a>
                <div class="article__content" data-job-id="111111"></div>
            </article>
            <article>
                <a class="article__header__focusable" href="/en_US/jobs/FolderDetail/Old-Job/222222">Old Job</a>
                <div class="article__content" data-job-id="222222"></div>
            </article>
        </html>
        """

        recent_detail = """
        <html>
            <meta name="Description" content="Recent Job at created  3-Sep-2026">
            <meta property="og:title" content="Recent Job">
            <div class="article__content__view__field posting-location">
                <div class="article__content__view__field__value">Berlin</div>
            </div>
            <article><h3>About the Role</h3><p>Description</p></article>
        </html>
        """
        old_detail = """
        <html>
            <meta name="Description" content="Old Job at created  1-Jan-2026">
            <meta property="og:title" content="Old Job">
            <div class="article__content__view__field posting-location">
                <div class="article__content__view__field__value">Berlin</div>
            </div>
            <article><h3>About the Role</h3><p>Description</p></article>
        </html>
        """

        mock_listing_resp = Mock()
        mock_listing_resp.text = listing_html
        mock_listing_resp.raise_for_status = Mock()

        mock_session.get.side_effect = [
            mock_listing_resp,
            Mock(text=recent_detail, raise_for_status=Mock()),
            Mock(text=old_detail, raise_for_status=Mock()),
        ]

        with patch("time.sleep", return_value=None):
            results = self.platform.fetch_jobs(self.site_config_no_filter, max_results=10)

        assert len(results) == 2
        assert results[0]["date_posted"] == "2026-09-03"
        assert results[1]["date_posted"] == "2026-01-01"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

