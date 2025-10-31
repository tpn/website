/* RevealBgVideoCtrl – adds play/pause to background videos
 * --------------------------------------------------------
 * Click anywhere on the slide   –OR–
 * press “V” to toggle the video.
 * Automatically pauses the clip when you leave the slide.
 */
window.RevealBgVideoCtrl = function () {
  return {
    id: "RevealBgVideoCtrl",
    init: (deck) => {

      function currentBgVideo () {
        const { h, v } = deck.getIndices();
        const bg   = deck.getSlideBackground(h, v);   // ← new
        const vid  = bg && bg.querySelector("video");
        //console.debug("[bg-video] background →", bg, "video →", vid);
        return vid;
      }

      function toggle () {
        const vid = currentBgVideo();
        if (vid) {
          //console.debug("[bg-video] toggling", vid.paused ? "play" : "pause");
          vid.paused ? vid.play() : vid.pause();
        }
      }

      /* — event hooks — */
      deck.getRevealElement().addEventListener("click", toggle);          // click anywhere
      deck.addKeyBinding({ keyCode: 86, key: "V" }, toggle);              // V key
      deck.on("slidechanged", e => {                                      // auto-pause when leaving
        const prevVid = e.previousSlide?.querySelector("video");
        if (prevVid && !prevVid.paused) prevVid.pause();
      });
    }
  };
};


