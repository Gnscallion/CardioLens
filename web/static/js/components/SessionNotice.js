/* 会话隔离提示条。
 *
 * 历史记录按浏览器隔离（没有账号体系），这件事必须让用户知道：
 * 否则他换一台设备打开，看到空的历史会以为"记录丢了"。
 * 与其让他猜，不如直接写在界面上。
 */
export default {
  name: 'SessionNotice',
  props: {
    compact: { type: Boolean, default: false },
  },
  template: `
    <div class="session-notice" data-test="session-notice">
      <span class="ic">🔒</span>
      <span v-if="compact">
        分析历史与本浏览器绑定。换设备或清除浏览器数据后，原记录将无法在此浏览器中访问。
      </span>
      <span v-else>
        <strong>分析历史与本浏览器绑定。</strong>
        本平台没有账号体系，历史记录用浏览器标识区分，因此你看不到别人的记录，
        别人也看不到你的。代价是：换一台设备、或清除浏览器数据之后，
        原记录将无法在此浏览器中访问（数据仍在服务器上，只是没有入口）。
      </span>
    </div>
  `,
};
