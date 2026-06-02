#include <iostream>

using namespace std;

int main(){
    long long n, x, y;

    cin >> n >> x >> y;


    long long a1 = y - n + 1;
    
    if (a1 > 0 && a1 * a1 >= x - n + 1){
        cout << a1 << " ";
        for (int i = 1; i < n; i++){
            cout << 1 << " ";
        }
    }
    else cout << -1;

    

}
