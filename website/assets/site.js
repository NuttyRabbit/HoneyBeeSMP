// The site sets no cookies. The only thing stored is whether this notice
// has been dismissed, and it never leaves the browser. That is why there
// is no consent gate here: there is nothing non-essential to consent to.
(function () {
  'use strict';

  var KEY = 'honeybee.cookie.notice';
  var banner = document.getElementById('cookie-banner');
  if (!banner) return;

  function remembered() {
    try {
      return window.localStorage.getItem(KEY) === 'dismissed';
    } catch (error) {
      // Private modes and blocked storage both land here. Show the notice,
      // because we cannot remember that it has been read.
      return false;
    }
  }

  if (remembered()) return;

  banner.hidden = false;

  banner.addEventListener('click', function (event) {
    var button = event.target.closest('[data-cookie-dismiss]');
    if (!button) return;

    try {
      window.localStorage.setItem(KEY, 'dismissed');
    } catch (error) {
      // Nothing to do: the notice is about to be hidden either way, it
      // will simply reappear on the next page.
    }

    banner.hidden = true;
  });
})();
