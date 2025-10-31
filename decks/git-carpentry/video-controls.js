// Toggle the current slide’s background video on click or when the user
// presses “v”.

document.addEventListener('DOMContentLoaded', () => {

  /** Return the <video> element that Reveal created for the current
   * slide. */
  function currentBgVideo() {
    const { h, v = 0 } = Reveal.getIndices();
    return document.querySelector(
      `.reveal .backgrounds .slide-background[data-index-h="${h}"][data-index-v="${v}"] video`
    );
  }

  /** Play or pause the video if it exists. */
  function toggle() {
    const vid = currentBgVideo();
    if (vid) {
      vid.paused ? vid.play() : vid.pause();
    }
  }

  // 1 · Click anywhere on the slide
  Reveal.getRevealElement().addEventListener('click', toggle);

  // 2 · Keyboard shortcut (V)
  document.addEventListener('keyup', e => {
    if (e.key.toLowerCase() === 'v') toggle();
  });

  // 3 · Optionally auto-pause when you leave the slide
  Reveal.on('slidechanged', event => {
    const prior = event.previousSlide
      && prior.querySelector('video');
    if (prior && !prior.paused) prior.pause();
  });
});

