/**
 * レスられ総研「参考になった」ボタンのカウンター（Google Apps Script）
 *
 * 使い方：script.google.com で新しいプロジェクトを作り、このファイルの中身を丸ごと貼る。
 * デプロイ →「新しいデプロイ」→ 種類「ウェブアプリ」、実行ユーザー「自分」、アクセスできるユーザー「全員」。
 * 発行された https://script.google.com/macros/s/…/exec を tools/build.py の LIKE_URL に入れる。
 *
 * 保存するのは「記事ID（NotionページIDの32桁）→ 件数」だけ。個人を特定する情報は受け取らない。
 *   ?a=get                 全記事の件数を返す
 *   ?a=like&k=<32桁>       1増やして新しい件数を返す
 *   ?a=unlike&k=<32桁>     1減らして新しい件数を返す（0未満にはしない）
 */
function doGet(e) {
  var p = (e && e.parameter) || {};
  var props = PropertiesService.getScriptProperties();
  if (p.a === "like" || p.a === "unlike") {
    var k = String(p.k || "");
    if (!/^[0-9a-f]{32}$/.test(k)) return out_({ error: "bad key" });
    var lock = LockService.getScriptLock();
    lock.waitLock(5000);
    try {
      var n = Number(props.getProperty(k) || 0) + (p.a === "like" ? 1 : -1);
      if (n < 0) n = 0;
      props.setProperty(k, String(n));
      return out_({ n: n });
    } finally {
      lock.releaseLock();
    }
  }
  var all = props.getProperties(), counts = {};
  Object.keys(all).forEach(function (k) {
    if (/^[0-9a-f]{32}$/.test(k)) counts[k] = Number(all[k]) || 0;
  });
  return out_({ counts: counts });
}

function out_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
