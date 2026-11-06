using System;
using System.IO;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
public static class Metadata {
 public static void Run(string root) {
  ISldWorks sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
  foreach(string path in Directory.GetFiles(root)) {
   string ext=Path.GetExtension(path).ToUpperInvariant();int type=ext==".SLDPRT"?1:ext==".SLDASM"?2:ext==".SLDDRW"?3:0;
   if(type==0||Path.GetFileName(path).StartsWith("~$"))continue;
   int e=0,w=0;IModelDoc2 m=(IModelDoc2)sw.OpenDoc6(path,type,1,"",ref e,ref w);
   for(int field=0;field<5;field++)typeof(IModelDoc2).GetProperty("SummaryInfo").SetValue(m,"",new object[]{field});
   m.Save3(1,ref e,ref w);if(e!=0)throw new Exception("Metadata save "+Path.GetFileName(path)+" "+e);
  }
 }
}
