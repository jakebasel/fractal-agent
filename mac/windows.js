// Lists TradingView windows the uploader can capture, left to right, one per line:
//   <window id>|<owner>|<x>|<y>|<w>|<h>|<title>
// Run by capture.sh:  osascript -l JavaScript windows.js "<title regex>" "<chrome bounds>"
// A window matches if (a) the app is TradingView (desktop app), (b) its title matches the regex
// (needs Screen Recording for osascript, otherwise titles are empty), or (c) it is a Google
// Chrome window whose bounds equal the Chrome window whose ACTIVE tab is tradingview.com
// (capture.sh asks Chrome for that via AppleScript, so no Screen Recording is needed).
ObjC.import('CoreGraphics');
function run(argv) {
  const re = new RegExp(argv[0] || 'TradingView', 'i');
  const chrome = (argv[1] || '').split(',').map(Number);   // left, top, right, bottom
  const list = ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo(1 | 16, 0))) || [];
  const near = (a, b) => Math.abs(a - b) <= 4;
  return list
    .filter(w => w.kCGWindowLayer === 0 && w.kCGWindowBounds && w.kCGWindowBounds.Width >= 400 &&
                 w.kCGWindowBounds.Height >= 300)
    .filter(w => {
      const b = w.kCGWindowBounds, owner = w.kCGWindowOwnerName || '';
      if (/tradingview/i.test(owner)) return true;
      if (re.test(w.kCGWindowName || '')) return true;
      return chrome.length === 4 && /chrome/i.test(owner) && near(b.X, chrome[0]) && near(b.Y, chrome[1]) &&
             near(b.X + b.Width, chrome[2]) && near(b.Y + b.Height, chrome[3]);
    })
    .sort((a, b) => a.kCGWindowBounds.X - b.kCGWindowBounds.X)
    .map(w => [w.kCGWindowNumber, w.kCGWindowOwnerName, Math.round(w.kCGWindowBounds.X),
               Math.round(w.kCGWindowBounds.Y), Math.round(w.kCGWindowBounds.Width),
               Math.round(w.kCGWindowBounds.Height), (w.kCGWindowName || '').replace(/\|/g, ' ')].join('|'))
    .join('\n');
}
