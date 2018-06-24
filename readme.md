# bilibili bangumi progress auto tracker

暂定这么个名字吧

## 介绍

在b站看番剧的同时一键在bgm.tv上标记已经看过的集数.


## 使用

https://greasyfork.org/zh-CN/scripts/369643-bgm-tv-auto-tracker 

安装后去 
[https://bgm.tv/oauth/authorize](https://bgm.tv/oauth/authorize?client_id=bgm2775b2797b4d958b&response_type=code&redirect_uri=https://bangumi-auto-tracker.trim21.cn/oauth_callback)
进行授权 

效果图 

![](./screenshot/bilibili.png) 
![](./screenshot/iqiyi.jpg) 
PS: 有添加优酷和其他什么乱七八糟网站支持的计划, 但是具体什么时候能加上就看心情了...(

## 开发

现在bangumi提供了官方api,又可以继续施工了.

bilibili部分已经完工了
现已支持iqiyi

欢迎贡献代码



server文件夹内是python服务端,基于python3.6.5的aiohttp

userscript是用`Grunt`编译成的,不要修改dist内的内容,

```bash
cd userscript

npm i #安装依赖
npm run dev # 检测文件变动,自动重新编译
```


在`Tampermonkey`中添加如下脚本,在修改脚本后刷新页面,最新脚本会自动起效
```javascript
// ==UserScript==
// @name         dev Bgm.tv auto tracker
// @namespace    https://trim21.me/
// @version      0.2.0
// @description  auto tracker your bangumi progress
// @author       Trim21
// @match        https://www.bilibili.com/bangumi/play/*
// @match        http*://www.iqiyi.com/*
// @match        https://bangumi-auto-tracker.trim21.cn/oauth_callback*
// @match        https://bangumi-auto-tracker.trim21.cn/userscript/options*
// @require      https://cdn.bootcss.com/jquery/3.3.1/jquery.js
// @require      https://cdn.bootcss.com/axios/0.18.0/axios.js
// @grant        GM_addStyle
// @grant        GM_xmlhttpRequest
// @grant        GM_getResourceText
// @grant        GM_setValue
// @grant        GM_openInTab
// @grant        GM_getValue
// @grant        unsafeWindow
// @connect      localhost
// @connect      api.bgm.tv
// @connect      bangumi-auto-tracker.trim21.cn
// @run-at       document-end
// @require      file:///path/to/bilibili-bangumi-tv-auto-tracker/userscript/env.js
// @require      file:///path/to/bilibili-bangumi-tv-auto-tracker/userscript/dist/latest/bgm-tv-auto-tracker.js
// ==/UserScript==
console.log('hello world')

```


## 已知问题

在同一集内重复点击`看到本集`会报错 这是api的设定

如果bgm的某个番没有对应条目(比如柯南的900+集),两个按钮均会报错

