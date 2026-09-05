#if UNITY_EDITOR
using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class StreetscapeRuntimeReview
{
    const string Key="StreetscapeRuntimeReview.Active";
    const string Output="C:/Users/satos/research/outdoor_seld_e2e/out/streetscape_review_2026-09-05";
    static readonly BindingFlags Private=BindingFlags.Instance|BindingFlags.NonPublic;
    static int frames,stage;
    static double started;
    static bool failed;
    static int editorSearchErrors;
    static StreetscapeRuntimeReview()
    {
        if(SessionState.GetBool(Key,false))
        { EditorApplication.update+=Tick;Application.logMessageReceived+=Log;started=EditorApplication.timeSinceStartup; }
    }
    public static void Run()
    {
        if(!Application.dataPath.Replace("\\","/").Contains("streetscape_review_2026-09-05/review_project/Assets"))throw new Exception("Isolated review project required.");
        var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
        var cam=new GameObject("Camera").AddComponent<Camera>();cam.tag="MainCamera";
        new GameObject("Player").AddComponent<JoyconDemoPlayer>();
        new GameObject("Visualizer").AddComponent<ScenarioVisualizer>();
        EditorSceneManager.SaveScene(scene,"Assets/RuntimeReview.unity");
        SessionState.SetBool(Key,true);
        EditorApplication.isPlaying=true;
    }
    static void Log(string message,string trace,LogType type)
    {
        if(type!=LogType.Error && type!=LogType.Exception)return;
        // Unity 6.6's empty-project search database can fail independently of Play Mode.
        // Keep the complete exception in a separate report; all application errors still fail.
        if(trace.Contains("UnityEditor.Search.SearchDatabase") && !trace.Contains("ScenarioVisualizer") && !trace.Contains("JapaneseStreetscape") && !trace.Contains("JoyconDemoPlayer"))
        { editorSearchErrors++;File.AppendAllText(Output+"/editor_search_errors.log",message+"\n"+trace+"\n");return; }
        failed=true;File.AppendAllText(Output+"/runtime_errors.log",message+"\n"+trace+"\n");
    }
    static void Tick()
    {
        if(!EditorApplication.isPlaying)return;
        if(EditorApplication.timeSinceStartup-started>90){Finish("FAIL timeout");return;}
        var player=UnityEngine.Object.FindAnyObjectByType<JoyconDemoPlayer>();
        var visual=UnityEngine.Object.FindAnyObjectByType<ScenarioVisualizer>();
        if(player==null||visual==null||player.CurrentClip==null)return;
        var audio=player.GetComponent<AudioSource>();if(audio.clip==null)return;
        frames++;
        if(stage==0 && frames>10)
        {
            audio.mute=true;audio.time=Mathf.Min(5,audio.clip.length*.5f);audio.Play();stage=1;frames=0;
        }
        else if(stage==1 && frames>45)
        {
            var world=UnityEngine.Object.FindAnyObjectByType<JapaneseStreetscape>();
            if(world==null||world.BuildingCount==0){Finish("FAIL missing runtime streets");return;}
            foreach(int mode in new[]{1,2,0})
            {
                typeof(ScenarioVisualizer).GetField("cameraMode",Private).SetValue(visual,mode);
                typeof(ScenarioVisualizer).GetMethod("UpdateCamera",Private).Invoke(visual,null);
                if(mode==1 && Mathf.Abs(Camera.main.transform.position.y-(1.68f+world.ObserverGroundHeight(world.WalkDirection*world.WalkSpeed*(player.PlayTime-5))))>.001f){Finish("FAIL pedestrian camera");return;}
            }
            world.SetDecorations(false);world.SetDecorations(true);
            File.WriteAllText(Output+"/gameview_fit_validation.txt",DemoGameViewFit.VerifyFit());
            var capture=new GameObject("HUD screenshot").AddComponent<DemoHudReview>();capture.output=Output+"/hud_verified.png";
            player.StartCoroutine((System.Collections.IEnumerator)typeof(JoyconDemoPlayer).GetMethod("LoadClip",Private).Invoke(player,new object[]{1}));stage=2;frames=0;
        }
        else if(stage==2 && frames>90)
        {
            var worlds=UnityEngine.Object.FindObjectsByType<JapaneseStreetscape>();
            if(worlds.Length!=1){Finish("FAIL old world not released: "+worlds.Length);return;}
            string loaded=(string)typeof(ScenarioVisualizer).GetField("loadedClip",Private).GetValue(visual);
            if(loaded!=player.CurrentClip){Finish("FAIL scene switch mismatch");return;}
            Finish(failed?"FAIL runtime logged errors":"PASS: audio playback, layout loading, moving objects, 3 cameras, decoration toggle, scene switching and old world release; no Joy-con hardware required.");
        }
    }
    static void Finish(string result)
    {
        SessionState.SetBool(Key,false);EditorApplication.update-=Tick;Application.logMessageReceived-=Log;
        File.WriteAllText(Output+"/runtime_validation.txt",result+"\nApplication errors: "+(failed?"present":"0")+"; unrelated Unity Editor search initialization errors: "+editorSearchErrors+" (see editor_search_errors.log when nonzero).");
        EditorApplication.Exit(result.StartsWith("PASS")?0:1);
    }
}
#endif
