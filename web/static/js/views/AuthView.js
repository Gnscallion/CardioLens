import { onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { store } from '../store.js';

export default {
  name: 'AuthView',
  setup() {
    const router = useRouter();
    const mode = ref('login');
    const username = ref('');
    const email = ref('');
    const password = ref('');
    const captcha = ref('');
    const captchaQuestion = ref('');
    const error = ref('');
    const busy = ref(false);
    const captchaLoading = ref(false);
    const account = ref(null);
    const currentPassword = ref('');
    const newPassword = ref('');
    const accountMessage = ref('');
    const accountBusy = ref(false);
    const resetMode = ref(false);
    const resetUsername = ref('');
    const resetToken = ref('');
    const resetPassword = ref('');

    async function loadCaptcha() {
      captchaLoading.value = true;
      error.value = '';
      captcha.value = '';
      try {
        const response = await fetch('/api/auth/captcha');
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || '验证码获取失败');
        captchaQuestion.value = data.question;
      } catch (err) { error.value = err.message; }
      finally { captchaLoading.value = false; }
    }

    async function submit() {
      busy.value = true;
      error.value = '';
      try {
        const payload = { username: username.value, password: password.value, email: email.value };
        if (mode.value === 'register') payload.captcha = captcha.value;
        const response = await fetch('/api/auth/' + mode.value, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '操作失败');
        router.push('/research');
      } catch (err) {
        error.value = err.message;
        if (mode.value === 'register') loadCaptcha();
      } finally { busy.value = false; }
    }

    function switchMode() { mode.value = mode.value === 'login' ? 'register' : 'login'; }
    async function requestReset() {
      error.value = '';
      try { const r = await fetch('/api/auth/password-reset/request', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({username_or_email: resetUsername.value}) }); const d = await r.json(); if (!r.ok) throw new Error(d.error || '请求失败'); resetToken.value = d.dev_token || ''; error.value = d.message + (d.dev_token ? '（开发环境已显示令牌）' : ''); }
      catch (err) { error.value = err.message; }
    }
    async function confirmReset() {
      error.value = '';
      try { const r = await fetch('/api/auth/password-reset/confirm', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({token: resetToken.value, new_password: resetPassword.value}) }); const d = await r.json(); if (!r.ok) throw new Error(d.error || '重置失败'); error.value = d.message; resetMode.value = false; }
      catch (err) { error.value = err.message; }
    }
    async function loadAccount() {
      try {
        const response = await fetch('/api/auth/me');
        const data = await response.json();
        account.value = data.user || null;
      } catch { account.value = null; }
    }
    async function changePassword() {
      accountBusy.value = true; accountMessage.value = '';
      try {
        const response = await fetch('/api/auth/password', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ current_password: currentPassword.value, new_password: newPassword.value }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '修改密码失败');
        currentPassword.value = ''; newPassword.value = '';
        accountMessage.value = '密码已修改';
        store.notify('密码已修改', 'ok');
      } catch (err) {
        accountMessage.value = err.message;
        store.notify(err.message, 'err');
      }
      finally { accountBusy.value = false; }
    }
    async function logout() {
      await fetch('/api/auth/logout', { method: 'POST' });
      account.value = null;
      accountMessage.value = '已退出登录';
      router.push('/');
    }
    watch(mode, (value) => { if (value === 'register') loadCaptcha(); });
    onMounted(() => {
      const params = new URLSearchParams(window.location.search);
      const token = params.get('token');
      if (token && params.get('reset') === '1') { resetMode.value = true; resetToken.value = token; }
      if (token && params.get('verify') === '1') {
        fetch('/api/auth/email-verification/confirm', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({token}) })
          .then((r) => r.json()).then((d) => { error.value = d.message || d.error || '邮箱验证完成'; });
      }
      loadAccount(); if (mode.value === 'register') loadCaptcha();
    });

    return { mode, username, email, password, captcha, captchaQuestion, error, busy, resetMode, resetUsername, resetToken, resetPassword, requestReset, confirmReset,
      captchaLoading, submit, switchMode, loadCaptcha, account, currentPassword,
      newPassword, accountMessage, accountBusy, changePassword, logout };
  },
  template: `
    <div class="card" style="max-width:480px;margin:40px auto" v-if="resetMode">
      <h1>找回密码</h1><p class="muted">输入注册时的账号或邮箱，开发环境会直接显示令牌；生产环境应由邮件服务发送链接。</p>
      <div class="field"><label for="reset-account">账号或邮箱</label><input id="reset-account" v-model="resetUsername" autocomplete="username"></div>
      <button class="btn btn-primary btn-block" @click="requestReset">发送重置链接</button>
      <div class="field mt16"><label for="reset-token">重置令牌</label><input id="reset-token" v-model="resetToken"></div>
      <div class="field"><label for="reset-password">新密码</label><input id="reset-password" v-model="resetPassword" type="password" placeholder="至少 8 位"></div>
      <button class="btn btn-primary btn-block" @click="confirmReset">确认重置</button>
      <button class="btn btn-ghost btn-block mt16" @click="resetMode=false">返回登录</button>
      <div class="alert alert-err mt16" v-if="error">{{ error }}</div>
    </div>
    <div class="card" style="max-width:480px;margin:40px auto" v-else-if="account">
      <h1>账户信息</h1>
      <p class="muted">已登录账号：{{ account.username }}</p>
      <div class="account-meta">
        <span>注册时间</span><strong>{{ account.created_at }}</strong>
        <span>最近登录</span><strong>{{ account.last_login || '本次登录' }}</strong>
      </div>
      <h2 class="mt16">修改密码</h2>
      <div class="field"><label for="current-password">当前密码</label><input id="current-password" v-model="currentPassword" type="password" autocomplete="current-password"></div>
      <div class="field"><label for="new-password">新密码</label><input id="new-password" v-model="newPassword" type="password" autocomplete="new-password" placeholder="至少 8 位"></div>
      <div data-test="account-message" class="alert" :class="accountMessage === '密码已修改' ? 'alert-ok' : 'alert-err'" v-if="accountMessage">{{ accountMessage }}</div>
      <button class="btn btn-primary btn-block" :disabled="accountBusy" @click="changePassword">{{ accountBusy ? '保存中…' : '保存新密码' }}</button>
      <button class="btn btn-ghost btn-block mt16" @click="logout">退出登录</button>
    </div>
    <div class="card auth-card" style="max-width:480px;margin:40px auto" v-else>
      <h1>{{ mode==='login'?'登录账号':'注册账号' }}</h1>
      <p class="muted">账号名在系统内唯一，密码仅保存为加盐哈希。</p>
      <div class="field"><label for="auth-user">账号名</label><input id="auth-user" v-model="username" autocomplete="username" placeholder="3-32 位账号名"></div>
      <div class="field"><label for="auth-password">密码</label><input id="auth-password" v-model="password" type="password" autocomplete="new-password" placeholder="至少 8 位"></div>
      <div class="field" v-if="mode==='register'"><label for="auth-email">邮箱（可选，用于找回密码）</label><input id="auth-email" v-model="email" type="email" autocomplete="email"></div>
      <div class="field" v-if="mode==='register'">
        <label for="auth-captcha">验证码</label>
        <div class="captcha-row">
          <input id="auth-captcha" v-model="captcha" inputmode="numeric" autocomplete="off" placeholder="请输入计算结果">
          <button type="button" class="captcha-question" :disabled="captchaLoading" @click="loadCaptcha">{{ captchaLoading ? '获取中…' : captchaQuestion || '点击获取' }}</button>
        </div>
        <p class="hint">验证码仅在本次注册中有效，点击题目可刷新。</p>
      </div>
      <div class="alert alert-err" v-if="error">{{ error }}</div>
      <button class="btn btn-primary btn-block" :disabled="busy || (mode==='register' && !captchaQuestion)" @click="submit">{{ busy?'处理中…':(mode==='login'?'登录':'注册并登录') }}</button>
      <button class="btn btn-ghost btn-block auth-secondary-btn" @click="switchMode">{{ mode==='login'?'没有账号？注册':'已有账号？登录' }}</button>
      <button v-if="mode==='login'" class="btn btn-ghost btn-block auth-secondary-btn" @click="resetMode=true">忘记密码？</button>
    </div>
  `,
};
