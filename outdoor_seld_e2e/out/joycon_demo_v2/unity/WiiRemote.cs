// WiiRemote.cs — Wii リモコンの振動ドライバ（2026-09-05）。JoyconLib 同梱の HIDapi で開き、出力レポート 0x10 の bit0 で振動 ON/OFF。
//
// Joy-con（HD 振動: 強さ 0〜1・周波数を指定できる）と違い、Wii リモコンの振動は偏心モーターの ON/OFF だけ。
// 強さは「周期 60 ms のうち ON にする時間の割合」で近似する（0.9 以上は常時 ON）。立ち上がりが遅いので 100 ms 未満のパルスは 100 ms に伸ばす。
// 機器層の仕様（README_機器層の仕様.md）はこの違いを吸収するために「振動子 k に 強さ・周波数・長さ」を送る形で書いてあり、
// Joy-con が 6 本そろったらこのドライバを外して Joy-con に差し替えるだけでよい。
//
// 接続: Windows の Bluetooth 設定で「Nintendo RVL-CNT-01」（-TR）をペアリング（1+2 同時押し、PIN なし）。
//       RVL-CNT-01-TR（後期型・MotionPlus 内蔵）は Windows の標準スタックで繋がらないことがある。
// 前提: シーンに JoyconManager があれば HIDapi.hid_init() 済み。無ければここで呼ぶ。

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using UnityEngine;

public class WiiRemote
{
    const ushort VENDOR = 0x057e;
    static readonly ushort[] PRODUCTS = { 0x0306, 0x0330 };     // RVL-CNT-01 / RVL-CNT-01-TR
    public const float PERIOD = 0.06f;          // ON/OFF の周期（20 Hz 弱）
    public const float MIN_PULSE = 0.10f;       // これより短いパルスは伸ばす（モーターの立ち上がり）
    public const float FULL_ON = 0.9f;          // これ以上の強さは常時 ON

    public IntPtr handle;
    public string path, product;
    public int index;
    bool on = false, warned = false;
    float amp = 0f, until = -1f, t0 = 0f;
    readonly byte[] buf = new byte[22];         // Windows の HID 出力は 22 バイトで送る（WiimoteLib と同じ）

    public static List<WiiRemote> Enumerate()
    {
        var list = new List<WiiRemote>();
        IntPtr top = HIDapi.hid_enumerate(VENDOR, 0x0);
        IntPtr ptr = top;
        while (ptr != IntPtr.Zero)
        {
            var info = (hid_device_info)Marshal.PtrToStructure(ptr, typeof(hid_device_info));
            if (Array.IndexOf(PRODUCTS, info.product_id) >= 0)
            {
                IntPtr h = HIDapi.hid_open_path(info.path);
                if (h != IntPtr.Zero)
                {
                    HIDapi.hid_set_nonblocking(h, 1);
                    var w = new WiiRemote { handle = h, path = info.path, product = $"0x{info.product_id:X4}", index = list.Count };
                    list.Add(w);
                    Debug.Log($"[Wii] connected #{w.index} product={w.product}");
                }
                else Debug.LogWarning("[Wii] hid_open_path failed: " + info.path);
            }
            ptr = info.next;
        }
        if (top != IntPtr.Zero) HIDapi.hid_free_enumeration(top);
        return list;
    }

    // 機器層からの指令: 強さ 0〜1 と長さ [ms]。周波数は無視（指定できない）
    public void Rumble(float amplitude, int ms)
    {
        float a = Mathf.Clamp01(amplitude);
        float end = Time.time + Mathf.Max(ms / 1000f, MIN_PULSE);
        if (end > until) until = end;
        if (a > amp || Time.time >= until - MIN_PULSE) amp = a;   // 強い方を優先。切れる直前なら上書き
        if (!on && amp >= FULL_ON) { Write(true); on = true; t0 = Time.time; }
    }

    // 毎フレーム呼ぶ: ON 時間の割合で強さを近似
    public void Tick()
    {
        bool want;
        if (Time.time >= until || amp <= 0f) want = false;
        else if (amp >= FULL_ON) want = true;
        else
        {
            float phase = (Time.time - t0) % PERIOD;
            want = phase < amp * PERIOD;
        }
        if (want != on) { Write(want); on = want; if (want) t0 = t0 == 0f ? Time.time : t0; }
        if (!want && Time.time >= until) { amp = 0f; t0 = 0f; }
    }

    public void SetLeds(int mask)
    {
        Array.Clear(buf, 0, buf.Length);
        buf[0] = 0x11; buf[1] = (byte)(((mask & 0xF) << 4) | (on ? 1 : 0));
        HIDapi.hid_write(handle, buf, (UIntPtr)buf.Length);
    }

    void Write(bool rumble)
    {
        Array.Clear(buf, 0, buf.Length);
        buf[0] = 0x10; buf[1] = (byte)(rumble ? 1 : 0);
        int r = HIDapi.hid_write(handle, buf, (UIntPtr)buf.Length);
        if (r < 0 && !warned) { warned = true; Debug.LogWarning($"[Wii] hid_write failed (#{index}). ペアリングと Bluetooth スタックを確認"); }
    }

    public void Close()
    {
        try { Write(false); HIDapi.hid_close(handle); } catch (Exception) { }
    }
}
