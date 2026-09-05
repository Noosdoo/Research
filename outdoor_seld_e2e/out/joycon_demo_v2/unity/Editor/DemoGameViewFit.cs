#if UNITY_EDITOR
using System;
using System.Reflection;
using UnityEditor;
using UnityEngine;

// Game View zoom crops the complete render, including every HUD edge. Fit the demo
// while it is playing; world-camera zoom remains available outside the HUD panels.
[InitializeOnLoad]
public static class DemoGameViewFit
{
    static double nextCheck;
    static readonly BindingFlags Flags=BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic;
    static DemoGameViewFit(){EditorApplication.update+=Update;}
    static void Update()
    {
        if(EditorApplication.timeSinceStartup<nextCheck)return;nextCheck=EditorApplication.timeSinceStartup+.5;
        if(!EditorApplication.isPlaying||UnityEngine.Object.FindAnyObjectByType<JoyconDemoPlayer>()==null)return;
        Fit();
    }
    public static string VerifyFit()
    {
        Type type=typeof(EditorWindow).Assembly.GetType("UnityEditor.GameView");
        if(type==null)throw new InvalidOperationException("Game View type unavailable");
        var window=EditorWindow.GetWindow(type);
        var min=type.GetProperty("minScale",Flags);var snap=type.GetMethod("SnapZoom",Flags);var scale=type.GetProperty("zoomAreaScale",Flags);
        if(min==null||snap==null||scale==null)throw new InvalidOperationException("Game View fitting API unavailable");
        snap.Invoke(window,new object[]{1.6f});Fit();
        float expected=(float)min.GetValue(window),actual=((Vector2)scale.GetValue(window)).y;
        if(Mathf.Abs(actual-expected)>.005f)throw new InvalidOperationException("Game View not fitted: "+actual+" / "+expected);
        return "PASS: 1.6x -> "+actual+"x (fit "+expected+"x)";
    }
    [MenuItem("Tools/Joycon/Fit Game View")]
    public static void Fit()
    {
        Type type=typeof(EditorWindow).Assembly.GetType("UnityEditor.GameView");if(type==null)return;
        var min=type.GetProperty("minScale",Flags);var snap=type.GetMethod("SnapZoom",Flags);
        var scale=type.GetProperty("zoomAreaScale",Flags);
        if(min==null||snap==null)return;
        foreach(var obj in Resources.FindObjectsOfTypeAll(type))
        {
            var window=obj as EditorWindow;if(window==null)continue;
            float fit=(float)min.GetValue(window);
            Vector2 current=scale!=null?(Vector2)scale.GetValue(window):Vector2.zero;
            if(Mathf.Abs(current.y-fit)>.005f){snap.Invoke(window,new object[]{fit});window.Repaint();}
        }
    }
}
#endif
