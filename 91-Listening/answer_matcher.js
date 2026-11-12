// Exact English spelling; flexible Chinese senses, without substring or typo matching.
function normalizeEnglish(value) {
  return String(value).normalize('NFKC').trim().toLowerCase().replace(/[’‘]/g, "'").replace(/[‐‑–—]/g, '-').replace(/\s+/g, ' ');
}
function normalizeChinese(value) {
  let text = String(value).normalize('NFKC').trim();
  text = text.replace(/[（(][^）)]*[）)]/g, '').replace(/^(?:意思是|意思为|指的是|是指)[:：]?/, '');
  text = text.replace(/[\s。.!！?？:：…·]/g, '');
  // Remove grammatical particles, never negation: “不真实” must not pass as “真实”.
  text = text.replace(/的$/, '');
  return text;
}
function matchChinese(value, accepted) {
  const targets = new Set(accepted.map(normalizeChinese).filter(Boolean));
  const parts = String(value).split(/[,，;；/、\n]+/).map(normalizeChinese).filter(Boolean);
  return parts.some(part => targets.has(part));
}
function checkListeningAnswer(english, chinese, word) {
  return { english: !!normalizeEnglish(english) && normalizeEnglish(english) === normalizeEnglish(word.word),
           chinese: matchChinese(chinese, word.acceptedZh || []) };
}
if (typeof module !== 'undefined') module.exports = { normalizeChinese, normalizeEnglish, matchChinese, checkListeningAnswer };
