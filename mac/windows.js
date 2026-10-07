// Prints "<window id> <x>" for each TradingView window, left to right.
// A window matches if its app is TradingView, or its title (the active browser tab) matches
// TV_MATCH. Run by capture.sh: osascript -l JavaScript windows.js "<regex>"
ObjC.import('CoreGraphics');
function run(argv) {
  const re = new RegExp(argv[0] || 'TradingView|MNQ|MES|MYM|NQ1!|ES1!', 'i');
  // 1 = all windows (also covered ones), 16 = exclude desktop elements
  const list = ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo(1 | 16, 0))) || [];
  return list
    .filter(w => w.kCGWindowLayer === 0 && w.kCGWindowBounds && w.kCGWindowBounds.Width >= 400 &&
                 w.kCGWindowBounds.Height >= 300 &&
                 (/tradingview/i.test(w.kCGWindowOwnerName || '') || re.test(w.kCGWindowName || '')))
    .sort((a, b) => a.kCGWindowBounds.X - b.kCGWindowBounds.X)
    .map(w => `${w.kCGWindowNumber} ${Math.round(w.kCGWindowBounds.X)}`)
    .join('\n');
}
