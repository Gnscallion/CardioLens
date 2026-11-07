/* 会话隔离提示条。
 *
 * 未登录时历史记录按浏览器隔离；登录后按账号隔离并可跨设备访问。
 * 这件事必须让用户知道，避免用户换设备后误以为记录丢失。
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
        未登录时分析历史与本浏览器绑定；登录后历史记录与账号绑定，可跨设备访问。
      </span>
      <span v-else>
        <strong>历史记录按登录状态保存。</strong>
        登录后，分析记录会与账号绑定，可以在其他设备登录后继续访问；
        未登录时，记录仅与当前浏览器绑定，因此换设备或清除浏览器数据后，
        原记录将无法在此浏览器中访问（数据仍在服务器上，只是没有账号入口）。
      </span>
    </div>
  `,
};
