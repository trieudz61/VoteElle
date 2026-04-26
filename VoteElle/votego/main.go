package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"mime/multipart"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"regexp"
	"strings"
	"sync/atomic"
	"time"
)

var (
	TARGET_ID   = "69e1ff11df6e31bd3fa4c707"
	CATEGORY    = "celebrity"
	URL_PATH    = "/elle-beauty-awards-2026/nhan-vat"
	NUM_WORKERS = 6

	SUPABASE_URL = "https://lzwxjlpmjfudlwesvsjp.supabase.co"
	SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6d3hqbHBtamZ1ZGx3ZXN2c2pwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcwNDYwNjAsImV4cCI6MjA5MjYyMjA2MH0.QK35Yykv-7RGLsgapTYtc85k757ZNiqqI4wCnrfGeAo"

	successCount int32
	failCount    int32
)

var vnNames = []string{
	"anh", "thy", "pham", "nguyen", "tran", "le", "hoang", "huynh", "phan", "vu", "vo", "dang",
	"bui", "do", "ho", "ngo", "duong", "ly", "thanh", "tuan", "minh", "hieu", "khoa", "phat",
	"dat", "son", "hai", "long", "thang", "tien", "quang", "tai", "thinh", "tinh", "bao",
	"tri", "duc", "trong", "sang", "linh", "trang", "ngoc", "mai", "lan", "huong", "phuong",
	"thu", "yen", "oanh", "vy", "my", "tram", "nhi", "chau", "nhung", "tuyen", "quy",
}

func init() {
	rand.Seed(time.Now().UnixNano())
	if envURL := os.Getenv("SUPABASE_URL"); envURL != "" {
		SUPABASE_URL = envURL
	}
	if envKey := os.Getenv("SUPABASE_KEY"); envKey != "" {
		SUPABASE_KEY = envKey
	}
}

func genUser() string {
	numWords := rand.Intn(2) + 2
	words := ""
	for i := 0; i < numWords; i++ {
		words += vnNames[rand.Intn(len(vnNames))]
	}
	suffixLen := rand.Intn(3) + 5
	suffix := ""
	for i := 0; i < suffixLen; i++ {
		suffix += fmt.Sprintf("%d", rand.Intn(10))
	}
	return words + suffix
}

func getFreshToken() string {
	client := &http.Client{Timeout: 10 * time.Second}
	req, _ := http.NewRequest("POST", SUPABASE_URL+"/rest/v1/rpc/pop_token", nil)
	req.Header.Set("apikey", SUPABASE_KEY)
	req.Header.Set("Authorization", "Bearer "+SUPABASE_KEY)
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return ""
	}
	body, _ := io.ReadAll(resp.Body)
	var tk string
	json.Unmarshal(body, &tk)
	if tk == "" {
		v := strings.TrimSpace(string(body))
		v = strings.Trim(v, `"`)
		return v
	}
	return tk
}

func waitForToken(workerID int, task string) string {
	fmt.Printf("[Worker-%d] Chờ token cho [%s]...\n", workerID, task)
	for {
		t := getFreshToken()
		if t != "" && t != "null" {
			fmt.Printf("[Worker-%d] [v] Có token cho [%s]!\n", workerID, task)
			return t
		}
		time.Sleep(3 * time.Second)
	}
}

func saveSupabase(workerID int, email, password, cookie string) {
	client := &http.Client{Timeout: 10 * time.Second}
	payload := map[string]string{
		"email":          email,
		"password":       password,
		"cookie_sid":     cookie,
		"last_time_vote": time.Now().UTC().Format(time.RFC3339),
	}
	body, _ := json.Marshal(payload)

	req, _ := http.NewRequest("POST", SUPABASE_URL+"/rest/v1/accounts", bytes.NewBuffer(body))
	req.Header.Set("apikey", SUPABASE_KEY)
	req.Header.Set("Authorization", "Bearer "+SUPABASE_KEY)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Prefer", "return=minimal")

	resp, err := client.Do(req)
	if err != nil {
		fmt.Printf("[Worker-%d] [-] Lỗi lưu DB: %v\n", workerID, err)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		fmt.Printf("[Worker-%d] [v] Đã lưu tài khoản lên Supabase!\n", workerID)
	} else {
		b, _ := io.ReadAll(resp.Body)
		fmt.Printf("[Worker-%d] [-] Lỗi lưu DB Code %d: %s\n", workerID, resp.StatusCode, string(b))
	}
}

type Field struct {
	Key string
	Val string
}

func createMultipart(fields []Field) (*bytes.Buffer, string) {
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	for _, f := range fields {
		writer.WriteField(f.Key, f.Val) 
	}
	writer.Close()
	return body, writer.FormDataContentType()
}

func runOneAccount(id int) bool {
	tokenReg := waitForToken(id, "Đăng Ký")
	tokenLogin := waitForToken(id, "Đăng Nhập")

	randomUser := genUser()
	email := fmt.Sprintf("%s@smvmail.com", randomUser)
	password := "Trieu@123"

	jar, _ := cookiejar.New(nil)
	client := &http.Client{
		Jar:     jar,
		Timeout: 30 * time.Second,
	}

	headersBase := map[string]string{
		"accept":          "text/x-component",
		"accept-language": "en-US,en;q=0.9,vi;q=0.8",
		"origin":          "https://events.elle.vn",
		"user-agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
	}

	// 1. REGISTER
	fmt.Printf("[Worker-%d] 1. Đăng ký: %s\n", id, email)
	fieldsReg := []Field{
		{"1_returnTo", "/"},
		{"1_username", randomUser},
		{"1_email", email},
		{"1_password", password},
		{"1_passwordConfirmation", password},
		{"1_cf-turnstile-response", tokenReg},
		{"1_cf-turnstile-response", tokenReg},
		{"0", `[{"error":"","success":""},"$K1"]`},
	}
	bodyReg, ctReg := createMultipart(fieldsReg)
	reqReg, _ := http.NewRequest("POST", "https://events.elle.vn/register", bodyReg)
	for k, v := range headersBase {
		reqReg.Header.Set(k, v)
	}
	reqReg.Header.Set("next-action", "ecb6a6ba19e2a6c226360a24043314cd2dffb8f8")
	reqReg.Header.Set("next-router-state-tree", "%5B%22%22%2C%7B%22children%22%3A%5B%22register%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fregister%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D")
	reqReg.Header.Set("referer", "https://events.elle.vn/register")
	reqReg.Header.Set("content-type", ctReg)

	respReg, err := client.Do(reqReg)
	if err != nil || respReg.StatusCode != 200 {
		fmt.Printf("[Worker-%d] [-] Đăng ký thất bại\n", id)
		if respReg != nil { respReg.Body.Close() }
		return false
	}
	respReg.Body.Close()
	fmt.Printf("[Worker-%d] [v] Đăng ký thành công!\n", id)
	time.Sleep(3 * time.Second)

	// 2. WAIT FOR EMAIL
	fmt.Printf("[Worker-%d] 2. Đang chờ email xác thực...\n", id)
	activationLink := ""
	re := regexp.MustCompile(`https://baseapi\.elle\.vn/auth/email-confirmation\?confirmation=[a-f0-9]+`)
	for attempt := 0; attempt < 12; attempt++ {
		time.Sleep(5 * time.Second)
		respMail, err := http.Get("https://smvmail.com/api/email?page=1&q=&email=" + email)
		if err == nil {
			body, _ := io.ReadAll(respMail.Body)
			respMail.Body.Close()
			content := strings.ReplaceAll(string(body), "\\/", "/")
			match := re.FindString(content)
			if match != "" {
				activationLink = match
				break
			}
		}
		fmt.Printf("[Worker-%d]   [%d/12] Chưa có mail...\n", id, attempt+1)
	}

	if activationLink == "" {
		fmt.Printf("[Worker-%d] [-] Timeout! Không tìm thấy email xác thực\n", id)
		return false
	}
	fmt.Printf("[Worker-%d] [v] Có link xác thực!\n", id)

	// 3. ACTIVATE
	fmt.Printf("[Worker-%d] 3. Kích hoạt tài khoản...\n", id)
	reqAct, _ := http.NewRequest("GET", activationLink, nil)
	respAct, err := client.Do(reqAct)
	if err != nil || (respAct.StatusCode != 200 && respAct.StatusCode != 303) {
		code := 0
		if respAct != nil { code = respAct.StatusCode }
		fmt.Printf("[Worker-%d] [-] Kích hoạt thất bại (%v)\n", id, code)
		if respAct != nil { respAct.Body.Close() }
		return false
	}
	respAct.Body.Close()
	fmt.Printf("[Worker-%d] [v] Kích hoạt thành công!\n", id)
	time.Sleep(1 * time.Second)

	// 4. LOGIN
	fmt.Printf("[Worker-%d] 4. Đăng nhập %s...\n", id, email)
	fieldsLogin := []Field{
		{"1_$ACTION_REF_1", ""},
		{"1_$ACTION_1:0", `{"id":"49be4f5334755d0610d3145cfc19c274abef2e1a","bound":"$@1"}`},
		{"1_$ACTION_1:1", `[{"error":""}]`},
		{"1_$ACTION_KEY", "k2964878165"},
		{"1_returnTo", "/elle-beauty-awards-2026"},
		{"1_identifier", email},
		{"1_password", password},
		{"1_cf-turnstile-response", tokenLogin},
		{"1_cf-turnstile-response", tokenLogin},
		{"0", `[{"error":""},"$K1"]`},
	}
	bodyLogin, ctLogin := createMultipart(fieldsLogin)
	reqLogin, _ := http.NewRequest("POST", "https://events.elle.vn/login?returnTo=%2Felle-beauty-awards-2026", bodyLogin)
	for k, v := range headersBase {
		reqLogin.Header.Set(k, v)
	}
	reqLogin.Header.Set("next-action", "49be4f5334755d0610d3145cfc19c274abef2e1a")
	reqLogin.Header.Set("next-router-state-tree", "%5B%22%22%2C%7B%22children%22%3A%5B%22login%22%2C%7B%22children%22%3A%5B%22__PAGE__%3F%7B%5C%22returnTo%5C%22%3A%5C%22%2Felle-beauty-awards-2026%5C%22%7D%22%2C%7B%7D%2C%22%2Flogin%3FreturnTo%3D%252Felle-beauty-awards-2026%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%2Ctrue%5D")
	reqLogin.Header.Set("referer", "https://events.elle.vn/login?returnTo=%2Felle-beauty-awards-2026")
	reqLogin.Header.Set("content-type", ctLogin)

	respLogin, err := client.Do(reqLogin)
	if err != nil {
		fmt.Printf("[Worker-%d] [-] Lỗi mạng khi đăng nhập\n", id)
		return false
	}
	
	voteSid := ""
	for _, c := range respLogin.Cookies() {
		if c.Name == "vote_sid" {
			voteSid = c.Value
		}
	}
	respLogin.Body.Close()

	if voteSid == "" {
		urlObj, _ := url.Parse("https://events.elle.vn")
		for _, c := range jar.Cookies(urlObj) {
			if c.Name == "vote_sid" {
				voteSid = c.Value
			}
		}
	}

	if voteSid == "" {
		fmt.Printf("[Worker-%d] [-] Không lấy được cookie login\n", id)
		return false
	}
	
	displaySid := voteSid
	if len(displaySid) > 16 {
		displaySid = displaySid[:16]
	}
	fmt.Printf("[Worker-%d] [v] Đăng nhập thành công! vote_sid: %s...\n", id, displaySid)

	// 5. VOTE
	fmt.Printf("[Worker-%d] 5. Đang vote cho %s...\n", id, TARGET_ID)
	votePayload := fmt.Sprintf(`["%s","%s","%s"]`, CATEGORY, TARGET_ID, URL_PATH)
	reqVote, _ := http.NewRequest("POST", "https://events.elle.vn"+URL_PATH, strings.NewReader(votePayload))
	for k, v := range headersBase {
		reqVote.Header.Set(k, v)
	}
	reqVote.Header.Set("content-type", "text/plain;charset=UTF-8")
	reqVote.Header.Set("next-action", "288bd3262db6e09085c5f3f89856bb17fb9abf1a")
	reqVote.Header.Set("next-router-state-tree", "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22slug%22%2C%22elle-beauty-awards-2026%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22nhan-vat%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Felle-beauty-awards-2026%2Fnhan-vat%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D")
	reqVote.Header.Set("referer", "https://events.elle.vn"+URL_PATH)

	respVote, err := client.Do(reqVote)
	if err != nil {
		fmt.Printf("[Worker-%d] [-] Vote thất bại (Lỗi HTTP)\n", id)
		return false
	}
	bodyVote, _ := io.ReadAll(respVote.Body)
	respVote.Body.Close()

	if respVote.StatusCode == 200 && !strings.Contains(string(bodyVote), `"ok":false`) {
		fmt.Printf("[Worker-%d] [v] VOTE THÀNH CÔNG!\n", id)
		saveSupabase(id, email, password, voteSid)
		return true
	} else {
		errMsg := string(bodyVote)
		if len(errMsg) > 150 {
			errMsg = errMsg[:150]
		}
		fmt.Printf("[Worker-%d] [-] Vote thất bại: %s\n", id, strings.TrimSpace(errMsg))
		return false
	}
}

func workerLoop(id int) {
	for {
		if runOneAccount(id) {
			atomic.AddInt32(&successCount, 1)
		} else {
			atomic.AddInt32(&failCount, 1)
		}
		fmt.Printf("\n  → Đã thành công: %d | Thất bại: %d\n\n", atomic.LoadInt32(&successCount), atomic.LoadInt32(&failCount))
	}
}

func main() {
	fmt.Println("=======================================================")
	fmt.Printf("  BẮT ĐẦU ĐĂNG KÝ & VOTE BẰNG GOLANG (%d luồng)\n", NUM_WORKERS)
	fmt.Println("=======================================================")

	for i := 1; i <= NUM_WORKERS; i++ {
		go workerLoop(i)
		time.Sleep(200 * time.Millisecond)
	}

	// Chặn process tắt
	select {}
}
