// Behaviours on a day page:
//   1. Track player: click a play button, plays the 30-sec preview.
//      When the preview ends, the next track with a preview auto-starts.
//   2. Play-album button: triggers the first playable track.
//   3. App-link smart fallback: links marked [data-app-link] try the
//      music:// URL scheme first (opens the Apple Music app on
//      macOS/iOS); if the page is still visible after a short delay
//      (no app handled it) we navigate to the https URL instead.

(() => {
  // ---- track player ----
  const list = document.querySelector('[data-player]');
  const audio = list ? new Audio() : null;
  if (audio) audio.preload = 'none';
  let current = null;

  const setPlayingState = (li, playing) => {
    if (!li) return;
    li.classList.toggle('is-playing', playing);
    const btn = li.querySelector('.play');
    if (btn) btn.classList.toggle('is-playing', playing);
  };

  const albumBtn = document.querySelector('[data-play-album]');
  const setAlbumBtnState = (playing) => {
    if (albumBtn) albumBtn.classList.toggle('is-playing', playing);
  };

  const stop = () => {
    audio.pause();
    setPlayingState(current, false);
    setAlbumBtnState(false);
    current = null;
  };

  const play = (li) => {
    const url = li.dataset.preview;
    if (!url) return;
    if (current === li) { stop(); return; }
    if (current) setPlayingState(current, false);
    current = li;
    setPlayingState(li, true);
    setAlbumBtnState(true);
    audio.src = url;
    audio.play().catch(() => {
      setPlayingState(li, false);
      setAlbumBtnState(false);
    });
  };

  if (list) {
    list.addEventListener('click', (e) => {
      const btn = e.target.closest('.play');
      if (!btn || btn.disabled) return;
      const li = btn.closest('.track');
      if (li) play(li);
    });

    audio.addEventListener('ended', () => {
      if (!current) return;
      let next = current.nextElementSibling;
      setPlayingState(current, false);
      current = null;
      while (next && !next.dataset.preview) next = next.nextElementSibling;
      if (next) play(next);
      else setAlbumBtnState(false);
    });
  }

  const playFirst = () => {
    const first = list && list.querySelector('.track[data-preview]:not([data-preview=""])');
    if (first) play(first);
  };

  if (albumBtn && list) {
    albumBtn.addEventListener('click', () => {
      if (current) { stop(); return; }
      playFirst();
    });
  }

  // Skip-prev / skip-next buttons: navigate within the current album.
  // If nothing is playing yet, both jump to the first track. At the
  // boundaries: prev at first track restarts it; next at last stops.
  document.querySelectorAll('[data-skip-prev]').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!list) return;
      if (!current) { playFirst(); return; }
      let prev = current.previousElementSibling;
      while (prev && !prev.dataset.preview) prev = prev.previousElementSibling;
      if (prev) play(prev);
      else if (audio) audio.currentTime = 0;
    });
  });
  document.querySelectorAll('[data-skip-next]').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (!list) return;
      if (!current) { playFirst(); return; }
      let next = current.nextElementSibling;
      while (next && !next.dataset.preview) next = next.nextElementSibling;
      if (next) play(next);
      else stop();
    });
  });

  // ---- accent toggle ----
  document.querySelectorAll('[data-accent-toggle]').forEach((btn) => {
    const html = document.documentElement;
    const sync = () => btn.setAttribute(
      'aria-pressed',
      String(!html.classList.contains('no-accent')),
    );
    sync();
    btn.addEventListener('click', () => {
      const turningOff = !html.classList.contains('no-accent');
      html.classList.toggle('no-accent', turningOff);
      try {
        localStorage.setItem('amcr.accent', turningOff ? 'off' : 'on');
      } catch (e) { /* ignore quota / private mode */ }
      sync();
    });
  });

})();
