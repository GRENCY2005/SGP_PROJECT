#include <stdio.h>
#include <conio.h>
int main() {

    int number1, number2, sum;
    clrscr();
    printf("Enter two integers: ");
    scanf("%d %d", &number1, &number2);

    // calculate the sum
    sum = number1 + number2;

    printf("%d + %d = %d", number1, number2, sum);
    getch();
   return 0;
}
