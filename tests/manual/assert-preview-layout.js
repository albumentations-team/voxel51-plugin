/* Run as an expression in the App page or the same-origin viewport harness.
 * Reads rendered DOM only. No page state or styles are modified.
 */
(() => {
  const doc = document.querySelector('iframe[title="FiftyOne laptop viewport"]')?.contentDocument ?? document;
  const win = doc.defaultView;
  const dialog = doc.querySelector('[role="dialog"]');
  if (!dialog) throw new Error('Open a completed augmentation preview first');
  const images = [...dialog.querySelectorAll('img[alt^="Preview "]')];
  if (!images.length || images.length % 3 !== 0) throw new Error('Expected three images per populated preview slot');
  const viewport = {width: win.innerWidth, height: win.innerHeight};
  const container = dialog.getBoundingClientRect();
  const measurements = images.map((img) => {
    const rect = img.getBoundingClientRect();
    const style = win.getComputedStyle(img);
    if (!img.complete || !img.naturalWidth || !img.naturalHeight) throw new Error(`${img.alt}: image missing or not loaded`);
    const expectedWidth = rect.height * img.naturalWidth / img.naturalHeight;
    const errorPx = Math.abs(rect.width - expectedWidth);
    if (rect.width <= 0 || rect.height <= 0 || errorPx > 1) throw new Error(`${img.alt}: distorted aspect ratio (${errorPx}px)`);
    if (style.objectFit !== 'contain') throw new Error(`${img.alt}: image may stretch or crop`);
    if (rect.left < container.left - 1 || rect.right > container.right + 1 || rect.right > viewport.width + 1) throw new Error(`${img.alt}: horizontal overflow`);
    if (rect.height > Math.min(360, viewport.height * 0.5) + 1) throw new Error(`${img.alt}: exceeds viewport height bound`);
    if (rect.width > img.naturalWidth + 1 || rect.height > img.naturalHeight + 1) throw new Error(`${img.alt}: image is enlarged`);
    return {alt: img.alt, natural: [img.naturalWidth, img.naturalHeight], rendered: [rect.width, rect.height], objectFit: style.objectFit, aspectErrorPx: errorPx};
  });
  if (doc.documentElement.scrollWidth > viewport.width + 1) throw new Error('The App has horizontal page overflow');
  return {viewport, slots: images.length / 3, images: measurements};
})()
