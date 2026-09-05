#if UNITY_EDITOR
using System.Collections;
using System.IO;
using UnityEngine;

public class DemoHudReview : MonoBehaviour
{
    public string output;
    IEnumerator Start()
    {
        yield return new WaitForSeconds(.4f);
        yield return null;
        // Request capture of the next completed frame, including IMGUI.
        ScreenCapture.CaptureScreenshot(output);
        File.WriteAllText(output+".txt",Screen.width+" x "+Screen.height+"; IMGUI included");
    }
}
#endif
