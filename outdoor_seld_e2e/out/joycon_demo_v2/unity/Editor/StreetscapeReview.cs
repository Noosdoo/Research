#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

// Run in an isolated review project. Does not open or save the user's scene.
public static class StreetscapeReview
{
    const string Source = "C:/Users/satos/research/outdoor_seld_e2e/out/joycon_demo_v2/場面";
    const string Output = "C:/Users/satos/research/outdoor_seld_e2e/out/streetscape_review_2026-09-05";
    static readonly BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
    public static void Run()
    {
        if (!Application.dataPath.Replace("\\", "/").Contains("streetscape_review_2026-09-05/review_project/Assets")) throw new Exception("Run only in the isolated review project.");
        Directory.CreateDirectory(Output+"/renders");
        var report=new List<string>{"index,scenario,buildings,roads,triangles,renderers,generation_ms,status"};
        string[] paths=Directory.GetFiles(Source,"*_layout.csv",SearchOption.AllDirectories);Array.Sort(paths,StringComparer.Ordinal);
        PedestrianRouteReview.ValidateHud();
        var routeReport=new List<string>{"index,scenario,route_geometry,status"};
        int errors=0;
        for(int index=0;index<paths.Length;index++)
        {
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            try
            {
                var watch=System.Diagnostics.Stopwatch.StartNew();
                var world=JapaneseStreetscape.Build(paths[index]);watch.Stop();
                string routeCheck=PedestrianRouteReview.Validate(world);
                routeReport.Add(index+",\""+Path.GetFileName(paths[index])+"\",\""+routeCheck+"\",PASS");
                File.WriteAllLines(Output+"/pedestrian_validation.csv",routeReport);
                JapaneseStreetscape.ConfigureLighting();
                var camera=new GameObject("Review camera").AddComponent<Camera>();camera.tag="MainCamera";
                camera.transform.position=new Vector3(0,25,-29);camera.transform.LookAt(new Vector3(0,0,7));
                camera.fieldOfView=52;camera.nearClipPlane=.1f;camera.farClipPlane=350;camera.clearFlags=CameraClearFlags.SolidColor;camera.backgroundColor=RenderSettings.fogColor;
                var person=GameObject.CreatePrimitive(PrimitiveType.Capsule);person.name="Observer";person.transform.localScale=new Vector3(.44f,.85f,.44f);person.transform.position=new Vector3(0,world.ObserverGroundHeight(0)+.85f,0);person.GetComponent<Renderer>().sharedMaterial=new Material(Shader.Find("Standard")){color=new Color(.85f,.49f,.21f)};
                AddVehicles(world,paths[index]);
                string name=Path.GetFileName(paths[index]).Replace("_layout.csv","");
                Capture(camera,Output+"/renders/"+index.ToString("D2")+"_"+name+".png",1200,800);
                if(index==0 || name.Contains("高架下") || name.Contains("正門前で待つ") || name.Contains("駐車場"))
                {
                    camera.transform.position=new Vector3(0,world.ObserverGroundHeight(0)+1.68f,-.25f);camera.transform.rotation=Quaternion.Euler(3,0,0);camera.fieldOfView=72;person.SetActive(false);
                    Capture(camera,Output+"/renders/"+index.ToString("D2")+"_street.png",1440,900);
                }
                foreach(var mf in world.GetComponentsInChildren<MeshFilter>())
                {
                    if(mf.sharedMesh==null || mf.sharedMesh.vertexCount==0)throw new Exception("Empty mesh");
                    Vector3 size=mf.sharedMesh.bounds.size;
                    if(float.IsNaN(size.x)||float.IsInfinity(size.y))throw new Exception("Invalid mesh bounds");
                }
                world.SetDecorations(false);
                world.SetDecorations(true);
                report.Add(index+",\""+paths[index].Substring(Source.Length+1)+"\","+world.BuildingCount+","+world.RoadCount+","+world.TriangleCount+","+world.GetComponentsInChildren<Renderer>().Length+","+watch.ElapsedMilliseconds+",PASS");
                Debug.Log("STREET_REVIEW "+index+" "+name+" PASS "+watch.ElapsedMilliseconds+" ms");
            }
            catch(Exception ex){errors++;report.Add(index+",\""+paths[index]+"\",0,0,0,0,0,FAIL: "+ex.Message);Debug.LogException(ex);}
            File.WriteAllLines(Output+"/scenario_validation.csv",report);
        }
        File.WriteAllText(Output+"/complete.txt",paths.Length+" scenarios; "+errors+" failures");
        if(Application.isBatchMode)
        {
            if(errors==0 && Array.IndexOf(Environment.GetCommandLineArgs(),"-streetRuntime")>=0)StreetscapeRuntimeReview.Run();
            else EditorApplication.Exit(errors==0?0:1);
        }
    }
    static void AddVehicles(JapaneseStreetscape world,string layout)
    {
        string file=layout.Replace("_layout.csv","_scene.csv");if(!File.Exists(file))return;
        var holder=new GameObject("Vehicle preview");var visual=holder.AddComponent<ScenarioVisualizer>();visual.enabled=false;
        typeof(ScenarioVisualizer).GetField("streets",Private).SetValue(visual,world);
        var classes=(Dictionary<string,string>)typeof(ScenarioVisualizer).GetField("objClass",Private).GetValue(visual);
        var latest=new Dictionary<string,string[]>();var previous=new Dictionary<string,string[]>();
        foreach(string line in File.ReadAllLines(file))
        {
            string[] p=line.Split(',');float t;
            if(p.Length<5||!float.TryParse(p[0],NumberStyles.Float,CultureInfo.InvariantCulture,out t)||t>5)continue;
            string[] before;if(latest.TryGetValue(p[1],out before))previous[p[1]]=before;latest[p[1]]=p;
        }
        var method=typeof(ScenarioVisualizer).GetMethod("GetOrCreate",Private);
        foreach(var pair in latest)
        {
            string[] p=pair.Value;classes[p[1]]=p[2];var go=(GameObject)method.Invoke(visual,new object[]{p[1]});
            float az=float.Parse(p[3],CultureInfo.InvariantCulture)*Mathf.Deg2Rad,d=float.Parse(p[4],CultureInfo.InvariantCulture);
            Vector3 position=new Vector3(-d*Mathf.Sin(az),go.transform.position.y,d*Mathf.Cos(az));go.transform.position=position;
            string[] before;if(previous.TryGetValue(p[1],out before))
            {
                float ba=float.Parse(before[3],CultureInfo.InvariantCulture)*Mathf.Deg2Rad,bd=float.Parse(before[4],CultureInfo.InvariantCulture);
                Vector3 delta=position-new Vector3(-bd*Mathf.Sin(ba),position.y,bd*Mathf.Cos(ba));if(delta.sqrMagnitude>.0001f)go.transform.rotation=Quaternion.LookRotation(delta);
            }
            // Audit labels stay in the application; clean review renders show physical assets.
            foreach(var label in go.GetComponentsInChildren<TextMesh>())label.gameObject.SetActive(false);
        }
    }
    static void Capture(Camera camera,string path,int width,int height)
    {
        var target=new RenderTexture(width,height,24){antiAliasing=4};target.Create();
        var old=RenderTexture.active;camera.targetTexture=target;camera.Render();RenderTexture.active=target;
        var image=new Texture2D(width,height,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,width,height),0,0);image.Apply();File.WriteAllBytes(path,image.EncodeToPNG());
        camera.targetTexture=null;RenderTexture.active=old;UnityEngine.Object.DestroyImmediate(image);target.Release();UnityEngine.Object.DestroyImmediate(target);
    }
}
#endif
