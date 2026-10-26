import { completedRunsAfter } from './jobFilters.js';

const PREFS = 'job-scout.alerts.v1', SEEN = 'job-scout.alerts.completed.v1';
function read(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
function write(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Private mode: session-only fallback. */ } }

export function createAlerts() {
  let settings = {...{sound:false, desktop:false}, ...read(PREFS, {})}, audio, seen = null;
  function beep() {
    if (audio?.state !== 'running') return;
    const oscillator = audio.createOscillator(), gain = audio.createGain(), start = audio.currentTime;
    oscillator.frequency.value = 740;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.12, start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.28);
    oscillator.connect(gain); gain.connect(audio.destination);
    oscillator.start(); oscillator.stop(start + 0.3);
    oscillator.onended = () => {oscillator.disconnect(); gain.disconnect();};
  }
  return {
    settings: () => ({...settings}),
    soundReady: () => audio?.state === 'running',
    async enableSound(enabled) {
      if (enabled) {
        const Context = window.AudioContext || window.webkitAudioContext;
        if (!Context) throw new Error('This browser does not support sound alerts.');
        audio ||= new Context();
        await audio.resume();
        if (audio.state !== 'running') throw new Error('Sound is blocked. Allow audio in your browser settings.');
        beep();
      }
      settings.sound = enabled; write(PREFS, settings);
      return {...settings};
    },
    async enableDesktop(enabled) {
      if (enabled) {
        if (!window.isSecureContext || !('Notification' in window))
          throw new Error('Desktop notifications need a supported browser on localhost or HTTPS.');
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') throw new Error('Notifications were not allowed. You can enable them in the browser site settings.');
      }
      settings.desktop = enabled; write(PREFS, settings);
      return {...settings};
    },
    async process(runs, notify) {
      const completed = completedRunsAfter(runs, -1), latest = Math.max(0, ...completed.map(run => run.id));
      // Establish a baseline on each page load; never replay historical results.
      if (seen === null) {seen = latest; write(SEEN, latest); return;}
      const pending = completedRunsAfter(runs, seen);
      if (!pending.length) return;
      const deliver = () => {
        const claimed = Math.max(seen, Number(read(SEEN, seen)) || 0);
        const unclaimed = pending.filter(run => run.id > claimed);
        seen = Math.max(seen, ...pending.map(run => run.id)); write(SEEN, seen);
        const count = unclaimed.reduce((total, run) => total + Number(run.details?.added || 0), 0);
        if (!count) return;
        const message = count + ' new job' + (count === 1 ? '' : 's') + ' available';
        notify(message);
        if (settings.sound) beep();
        if (settings.desktop && 'Notification' in window && Notification.permission === 'granted') {
          try {
            const notification = new Notification('Job Scout · Scrape complete', {body:message, tag:'job-scout-run-' + seen});
            notification.onclick = () => {window.focus(); notification.close();};
          } catch { /* Unsupported desktop API: keep the in-app alert. */ }
        }
      };
      if (navigator.locks) await navigator.locks.request('job-scout-result-alerts', deliver);
      else deliver();
    }
  };
}
