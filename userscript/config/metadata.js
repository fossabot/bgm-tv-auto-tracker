const pkg = require('../package.json')

module.exports = {
  'name': 'Bgm.tv auto tracker',
  'namespace': 'https://trim21.me/',
  'version': pkg['version'],
  'author': pkg['author'],
  'source': pkg['repository']['url'],
  'license': 'MIT',
  'match': [
    'https://www.bilibili.com/bangumi/play/*',
    'http*://www.iqiyi.com/*',
    'https://bangumi-auto-tracker.trim21.cn/oauth_callback*',
    'https://bangumi-auto-tracker.trim21.cn/userscript/options*'
  ],
  'require': [
    'https://cdn.bootcss.com/jquery/3.3.1/jquery.min.js',
    'https://cdn.bootcss.com/axios/0.18.0/axios.js'
  ],
  'grant': [
    'GM_addStyle',
    'GM_setValue',
    'GM_getValue',
    'GM_openInTab',
    'GM_addStyle',
    'GM_xmlhttpRequest',
    'unsafeWindow'
  ],
  'connect': [
    'localhost',
    'api.bgm.tv',
    'bangumi-auto-tracker.trim21.cn'
  ],
  'run-at': 'document-end'
}