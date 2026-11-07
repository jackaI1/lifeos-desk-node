package ca.jacklai.desklink
import android.app.Activity
import android.os.Bundle
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.widget.*
import org.json.JSONObject
import java.net.InetSocketAddress
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity: Activity() {
 private val executor=Executors.newSingleThreadExecutor()
 private val cancelled=AtomicBoolean(false)
 private var callback: ConnectivityManager.NetworkCallback?=null
 private lateinit var manager: ConnectivityManager
 override fun onCreate(state:Bundle?) {
  super.onCreate(state);manager=getSystemService(ConnectivityManager::class.java)
  val layout=LinearLayout(this);layout.orientation=LinearLayout.VERTICAL
  val host=EditText(this);host.hint="TLS broker hostname (TCP 443)"
  val result=TextView(this)
  val wifi=Button(this);wifi.text="Measure Wi-Fi"
  val cellular=Button(this);cellular.text="Measure cellular"
  layout.addView(host);layout.addView(wifi);layout.addView(cellular);layout.addView(result);setContentView(layout)
  fun measure(transport:Int,name:String){
   callback?.let{manager.unregisterNetworkCallback(it)}
   val hostname=host.text.toString().trim()
   if(!Regex("[A-Za-z0-9.-]{1,253}").matches(hostname)){result.text="Enter a hostname";return}
   val request=NetworkRequest.Builder().addTransportType(transport).addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build()
   val handled=AtomicBoolean(false)
   val next=object: ConnectivityManager.NetworkCallback(){
    override fun onAvailable(network:Network){if(!handled.compareAndSet(false,true))return
     executor.submit{
      try{
       val ip=network.getByName(hostname);val start=System.nanoTime()
       network.socketFactory.createSocket().use{socket->socket.connect(InetSocketAddress(ip,443),3000)}
       val row=JSONObject().put("transport",name).put("rtt_ms",(System.nanoTime()-start)/1e6).put("kind","tcp_connect").put("timestamp_ms",System.currentTimeMillis())
       openFileOutput("measurements.jsonl",MODE_APPEND).use{it.write((row.toString()+"\n").toByteArray())}
       if(!cancelled.get())runOnUiThread{result.text=row.toString()}
      }catch(error:Exception){if(!cancelled.get())runOnUiThread{result.text="Probe failed: ${error.javaClass.simpleName}"}}
     }
    }
    override fun onUnavailable(){runOnUiThread{result.text="Requested network unavailable"}}
   }
   callback=next;manager.requestNetwork(request,next,5000)
  }
  wifi.setOnClickListener{measure(NetworkCapabilities.TRANSPORT_WIFI,"wifi")}
  cellular.setOnClickListener{measure(NetworkCapabilities.TRANSPORT_CELLULAR,"cellular")}
 }
 override fun onDestroy(){cancelled.set(true);callback?.let{manager.unregisterNetworkCallback(it)};executor.shutdownNow();super.onDestroy()}
}
